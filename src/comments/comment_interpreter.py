"""CommentInterpreter for parsing and executing user commands in task notes."""

import re
from datetime import date, timedelta
from typing import Optional

from src.analyzer.models import Priority
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

    def __init__(self, task_manager: Optional[TaskManager] = None):
        """Initialize the CommentInterpreter.

        Args:
            task_manager: TaskManager instance for task operations.
                Created automatically if not provided.
        """
        self._task_manager = task_manager

    def _get_task_manager(self) -> TaskManager:
        """Get or create the TaskManager."""
        if self._task_manager is None:
            self._task_manager = TaskManager()
        return self._task_manager

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

    _HANDLERS = {
        CommandType.PRIORITY: _execute_priority,
        CommandType.DUE: _execute_due,
        CommandType.SNOOZE: _execute_snooze,
        CommandType.IGNORE: _execute_ignore,
        CommandType.DELETE: _execute_delete,
        CommandType.NOTE: _execute_note,
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
