"""CommentInterpreter for parsing and executing user commands in task notes."""

import base64
import re
from datetime import date, timedelta
from email.mime.text import MIMEText
from typing import Optional

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from src.analyzer.models import Priority
from src.fetcher.gmail_auth import GmailAuthenticator
from src.tasks.models import Task
from src.tasks.task_manager import TaskManager

from .exceptions import CommentExecutionError
from .models import CommandResult, CommandType, ParsedCommand, ProcessingResult

# Sentinel action returned by @delete handler
_DELETE_ACTION = "__DELETE__"


class CommentInterpreter:
    """Parses and executes user commands embedded in Google Task notes.

    Users write commands in their task notes using the @command syntax.
    The interpreter scans tasks, parses commands, executes them via
    TaskManager, and removes processed commands from notes.
    """

    COMMAND_PATTERN = re.compile(r"^@(\w+)\s*(.*?)\s*$", re.IGNORECASE)

    COMMAND_MAP: dict[str, CommandType] = {
        "priority": CommandType.PRIORITY,
        "due": CommandType.DUE,
        "snooze": CommandType.SNOOZE,
        "ignore": CommandType.IGNORE,
        "delete": CommandType.DELETE,
        "note": CommandType.NOTE,
        "respond": CommandType.RESPOND,
    }

    PRIORITY_MAP: dict[str, Priority] = {
        "low": Priority.LOW,
        "medium": Priority.MEDIUM,
        "high": Priority.HIGH,
        "urgent": Priority.URGENT,
    }

    SNOOZE_UNITS: dict[str, int] = {
        "day": 1,
        "days": 1,
        "week": 7,
        "weeks": 7,
    }

    def __init__(
        self,
        task_manager: Optional[TaskManager] = None,
        authenticator: Optional[GmailAuthenticator] = None,
        gmail_service: Optional[Resource] = None,
    ):
        """Initialize the CommentInterpreter.

        Args:
            task_manager: TaskManager instance for task operations.
                Created automatically if not provided.
            authenticator: GmailAuthenticator for Gmail API access.
                Created with defaults if not provided. Only used by @respond.
            gmail_service: Pre-configured Gmail API service for testing.
                Takes precedence over authenticator.
        """
        self._task_manager = task_manager
        self._authenticator = authenticator
        self._gmail_service = gmail_service

    def _get_task_manager(self) -> TaskManager:
        """Get or create the TaskManager."""
        if self._task_manager is None:
            self._task_manager = TaskManager()
        return self._task_manager

    def _get_gmail_service(self) -> Resource:
        """Get or create the Gmail API service for sending replies."""
        if self._gmail_service is None:
            if self._authenticator is None:
                self._authenticator = GmailAuthenticator()
            self._gmail_service = self._authenticator.get_service()
        return self._gmail_service

    # -------------------- Parsing --------------------

    def parse_commands(self, notes: Optional[str]) -> list[ParsedCommand]:
        """Parse all @commands from a task's notes text.

        Only processes recognized commands. Unrecognized @-prefixed lines
        are silently skipped.

        Args:
            notes: The notes string from a Task (already stripped of metadata).

        Returns:
            List of ParsedCommand objects found in the notes.
        """
        if not notes:
            return []

        commands = []
        for line in notes.splitlines():
            match = self.COMMAND_PATTERN.match(line)
            if not match:
                continue

            keyword = match.group(1).lower()
            if keyword not in self.COMMAND_MAP:
                continue

            commands.append(
                ParsedCommand(
                    command_type=self.COMMAND_MAP[keyword],
                    raw_text=line,
                    arguments=match.group(2),
                )
            )

        return commands

    def strip_commands(
        self, notes: Optional[str], commands: list[ParsedCommand]
    ) -> str:
        """Remove processed command lines from notes.

        Args:
            notes: Original notes string.
            commands: Commands that were parsed and will be processed.

        Returns:
            Notes with command lines removed, whitespace-trimmed.
        """
        if not notes:
            return ""

        raw_texts = {cmd.raw_text for cmd in commands}
        remaining = [
            line for line in notes.splitlines() if line not in raw_texts
        ]

        # Collapse multiple consecutive blank lines
        cleaned: list[str] = []
        for line in remaining:
            if line.strip() == "" and cleaned and cleaned[-1].strip() == "":
                continue
            cleaned.append(line)

        return "\n".join(cleaned).strip()

    # -------------------- Command Execution --------------------

    def _execute_priority(self, task: Task, command: ParsedCommand) -> str:
        """Change the priority in the task's notes text."""
        level = command.arguments.lower()
        if level not in self.PRIORITY_MAP:
            valid = ", ".join(self.PRIORITY_MAP.keys())
            raise CommentExecutionError(
                "priority",
                task.id or "",
                f"Invalid priority '{command.arguments}'. Valid values: {valid}",
            )

        new_priority = self.PRIORITY_MAP[level]
        priority_pattern = re.compile(r"^Priority:\s*\w+", re.MULTILINE)

        if task.notes and priority_pattern.search(task.notes):
            task.notes = priority_pattern.sub(
                f"Priority: {new_priority.value}", task.notes
            )
        else:
            prefix = f"Priority: {new_priority.value}"
            task.notes = f"{prefix}\n\n{task.notes}" if task.notes else prefix

        return f"Priority changed to {new_priority.value}"

    def _execute_due(self, task: Task, command: ParsedCommand) -> str:
        """Set the task's due date to an absolute date."""
        try:
            new_due = date.fromisoformat(command.arguments)
        except ValueError:
            raise CommentExecutionError(
                "due",
                task.id or "",
                f"Invalid date format '{command.arguments}'. Use YYYY-MM-DD.",
            )

        task.due = new_due
        return f"Due date set to {new_due.isoformat()}"

    def _execute_snooze(self, task: Task, command: ParsedCommand) -> str:
        """Push the task's due date forward by a relative offset."""
        parts = command.arguments.split()
        if len(parts) != 2:
            raise CommentExecutionError(
                "snooze",
                task.id or "",
                f"Invalid snooze format '{command.arguments}'. Use '@snooze <N> <days|weeks>'.",
            )

        try:
            amount = int(parts[0])
        except ValueError:
            raise CommentExecutionError(
                "snooze",
                task.id or "",
                f"Invalid number '{parts[0]}'.",
            )

        unit = parts[1].lower()
        if unit not in self.SNOOZE_UNITS:
            valid = ", ".join(sorted(set(self.SNOOZE_UNITS.keys())))
            raise CommentExecutionError(
                "snooze",
                task.id or "",
                f"Invalid time unit '{parts[1]}'. Valid units: {valid}.",
            )

        days = amount * self.SNOOZE_UNITS[unit]
        base_date = task.due or date.today()
        task.due = base_date + timedelta(days=days)
        return f"Due date snoozed to {task.due.isoformat()}"

    def _execute_ignore(self, task: Task, command: ParsedCommand) -> str:
        """Mark the task as completed (dismiss/ignore)."""
        task.mark_completed()
        return "Task marked as completed (ignored)"

    def _execute_delete(self, task: Task, command: ParsedCommand) -> str:
        """Flag the task for deletion."""
        return _DELETE_ACTION

    def _execute_note(self, task: Task, command: ParsedCommand) -> str:
        """Append additional text to the task's notes."""
        text = command.arguments
        if task.notes:
            task.notes = f"{task.notes}\n{text}"
        else:
            task.notes = text
        return f"Note appended: {text}"

    def _fetch_original_email_headers(self, message_id: str) -> dict[str, str]:
        """Fetch headers needed for replying to the original email.

        Args:
            message_id: Gmail message ID of the original email.

        Returns:
            Dict with keys: 'from', 'subject', 'message_id'.

        Raises:
            CommentExecutionError: If the email cannot be fetched.
        """
        service = self._get_gmail_service()
        try:
            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Message-ID"],
                )
                .execute()
            )
        except HttpError as e:
            raise CommentExecutionError(
                "respond", message_id, f"Failed to fetch original email: {e}"
            )

        headers = message.get("payload", {}).get("headers", [])
        header_map = {h["name"].lower(): h["value"] for h in headers}

        return {
            "from": header_map.get("from", ""),
            "subject": header_map.get("subject", "(No Subject)"),
            "message_id": header_map.get("message-id", ""),
        }

    def _execute_respond(self, task: Task, command: ParsedCommand) -> str:
        """Send a reply to the original email thread and mark task completed."""
        if not task.source_thread_id:
            raise CommentExecutionError(
                "respond",
                task.id or "",
                "Task has no source email thread. Cannot send reply.",
            )
        if not task.source_email_id:
            raise CommentExecutionError(
                "respond",
                task.id or "",
                "Task has no source email ID. Cannot send reply.",
            )

        message_body = command.arguments.strip()
        if not message_body:
            raise CommentExecutionError(
                "respond",
                task.id or "",
                "Reply message is empty. Use '@respond <your message>'.",
            )

        original = self._fetch_original_email_headers(task.source_email_id)

        if not original["from"]:
            raise CommentExecutionError(
                "respond",
                task.id or "",
                "Could not determine recipient from original email.",
            )

        subject = original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        mime_message = MIMEText(message_body)
        mime_message["to"] = original["from"]
        mime_message["subject"] = subject
        if original["message_id"]:
            mime_message["In-Reply-To"] = original["message_id"]
            mime_message["References"] = original["message_id"]

        raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()

        service = self._get_gmail_service()
        try:
            service.users().messages().send(
                userId="me",
                body={"raw": raw, "threadId": task.source_thread_id},
            ).execute()
        except HttpError as e:
            raise CommentExecutionError(
                "respond", task.id or "", f"Failed to send reply: {e}"
            )

        task.mark_completed()
        return f"Reply sent to {original['from']} and task marked as completed"

    _HANDLERS = {
        CommandType.PRIORITY: _execute_priority,
        CommandType.DUE: _execute_due,
        CommandType.SNOOZE: _execute_snooze,
        CommandType.IGNORE: _execute_ignore,
        CommandType.DELETE: _execute_delete,
        CommandType.NOTE: _execute_note,
        CommandType.RESPOND: _execute_respond,
    }

    # -------------------- Task Processing --------------------

    def _process_task(
        self, task: Task, list_id: Optional[str] = None
    ) -> list[CommandResult]:
        """Process all commands found in a single task's notes.

        Args:
            task: The Task to process.
            list_id: Task list ID for API calls.

        Returns:
            List of CommandResult for each command found.
        """
        commands = self.parse_commands(task.notes)
        if not commands:
            return []

        results: list[CommandResult] = []
        should_delete = False

        for command in commands:
            handler = self._HANDLERS.get(command.command_type)
            if handler is None:
                continue

            try:
                action = handler(self, task, command)
                if action == _DELETE_ACTION:
                    should_delete = True
                    action = "Task flagged for deletion"
                results.append(
                    CommandResult(
                        task_id=task.id or "",
                        task_title=task.title,
                        command=command,
                        success=True,
                        action_taken=action,
                    )
                )
            except CommentExecutionError as e:
                results.append(
                    CommandResult(
                        task_id=task.id or "",
                        task_title=task.title,
                        command=command,
                        success=False,
                        error=str(e),
                    )
                )

        # Clean processed commands from notes
        successful_commands = [r.command for r in results if r.success]
        task.notes = self.strip_commands(task.notes, successful_commands)

        # Apply changes via TaskManager
        tm = self._get_task_manager()
        if should_delete:
            tm.delete_task(task.id, list_id)
        else:
            tm.update_task(task, list_id)

        return results

    # -------------------- Main Entry Point --------------------

    def process_pending_tasks(
        self,
        list_id: Optional[str] = None,
    ) -> ProcessingResult:
        """Scan all pending tasks for user commands and execute them.

        Args:
            list_id: Task list ID. Uses default list if not specified.

        Returns:
            ProcessingResult with per-command outcomes and aggregate stats.
        """
        result = ProcessingResult()

        try:
            tm = self._get_task_manager()
            tasks = list(tm.list_tasks(list_id=list_id, show_completed=False))
        except Exception as e:
            result.add_error(f"Failed to list tasks: {e}")
            return result

        result.tasks_scanned = len(tasks)

        for task in tasks:
            try:
                command_results = self._process_task(task, list_id)
                result.commands_found += len(command_results)
                result.commands_executed += sum(
                    1 for r in command_results if r.success
                )
                result.results.extend(command_results)
            except Exception as e:
                result.add_error(
                    f"Error processing task '{task.title}' ({task.id}): {e}"
                )

        return result
