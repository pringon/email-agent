"""DigestReporter for generating daily task digest reports."""

import base64
from datetime import date, timedelta
from email.mime.text import MIMEText
from typing import Optional

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from src.fetcher.gmail_auth import DEFAULT_SCOPES as GMAIL_DEFAULT_SCOPES
from src.fetcher.gmail_auth import GmailAuthenticator
from src.tasks.task_manager import TaskManager

from .exceptions import DigestBuildError, DigestDeliveryError
from .models import DeliveryResult, DigestReport, DigestSection

# Gmail scope required for sending emails
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class DigestReporter:
    """Generates and delivers daily digest reports of pending tasks.

    Compiles task data from Google Tasks into a formatted summary,
    delivered as plain text output and optionally as an email.
    """

    def __init__(
        self,
        task_manager: Optional[TaskManager] = None,
        authenticator: Optional[GmailAuthenticator] = None,
        gmail_service: Optional[Resource] = None,
    ):
        """Initialize the DigestReporter.

        Args:
            task_manager: TaskManager instance for fetching tasks.
                Created automatically if not provided.
            authenticator: GmailAuthenticator for sending digest emails.
                Created with gmail.send scope if not provided.
            gmail_service: Pre-built Gmail API service resource.
                Overrides authenticator if provided.
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
        """Get or create the Gmail API service with send scope."""
        if self._gmail_service is None:
            if self._authenticator is None:
                scopes = list(GMAIL_DEFAULT_SCOPES) + [GMAIL_SEND_SCOPE]
                self._authenticator = GmailAuthenticator(scopes=scopes)
            self._gmail_service = self._authenticator.get_service()
        return self._gmail_service

    def _categorize_tasks(self, tasks: list) -> list[DigestSection]:
        """Group tasks into sections by due date proximity.

        Args:
            tasks: List of Task objects to categorize.

        Returns:
            Ordered list of non-empty DigestSections.
        """
        today = date.today()
        week_end = today + timedelta(days=7)

        overdue = []
        due_today = []
        due_this_week = []
        due_later = []
        no_due_date = []

        for task in tasks:
            if task.due is None:
                no_due_date.append(task)
            elif task.due < today:
                overdue.append(task)
            elif task.due == today:
                due_today.append(task)
            elif task.due <= week_end:
                due_this_week.append(task)
            else:
                due_later.append(task)

        sections = []
        if overdue:
            sections.append(DigestSection(heading="Overdue", tasks=overdue))
        if due_today:
            sections.append(DigestSection(heading="Due Today", tasks=due_today))
        if due_this_week:
            sections.append(DigestSection(heading="Due This Week", tasks=due_this_week))
        if due_later:
            sections.append(DigestSection(heading="Due Later", tasks=due_later))
        if no_due_date:
            sections.append(DigestSection(heading="No Due Date", tasks=no_due_date))

        return sections

    def _format_task_line(self, task) -> str:
        """Format a single task as a plain text line.

        Args:
            task: Task object to format.

        Returns:
            Formatted string like "- [ ] Task title (due: 2026-02-15)".
        """
        line = f"- [ ] {task.title}"
        if task.due is not None:
            line += f" (due: {task.due.isoformat()})"
        return line

    # -------------------- Public API --------------------

    def build_report(self, list_id: Optional[str] = None) -> DigestReport:
        """Build a digest report from current pending tasks.

        Args:
            list_id: Task list ID to report on. Uses default list if not specified.

        Returns:
            DigestReport with categorized pending tasks.

        Raises:
            DigestBuildError: If unable to fetch tasks.
        """
        try:
            tm = self._get_task_manager()
            task_list = tm.get_or_create_default_list()
            effective_list_id = list_id or task_list.id
            task_list_name = task_list.title

            tasks = list(tm.list_tasks(list_id=effective_list_id, show_completed=False))
        except Exception as e:
            raise DigestBuildError(str(e)) from e

        sections = self._categorize_tasks(tasks)

        overdue_count = 0
        for section in sections:
            if section.heading == "Overdue":
                overdue_count = section.count
                break

        return DigestReport(
            sections=sections,
            total_pending=len(tasks),
            total_overdue=overdue_count,
            task_list_name=task_list_name,
        )

    def format_plain_text(self, report: DigestReport) -> str:
        """Format a digest report as plain text.

        Args:
            report: DigestReport to format.

        Returns:
            Formatted plain text string.
        """
        separator = "=" * 40
        lines = []

        # Header
        lines.append(separator)
        lines.append("  Daily Task Digest")
        lines.append(f"  Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M')}")
        if report.task_list_name:
            lines.append(f"  Task List: {report.task_list_name}")
        lines.append(separator)
        lines.append("")

        if report.is_empty:
            lines.append("No pending tasks. You're all caught up!")
        else:
            # Summary line
            summary = f"Summary: {report.total_pending} pending task"
            if report.total_pending != 1:
                summary += "s"
            if report.total_overdue > 0:
                summary += f" ({report.total_overdue} overdue)"
            lines.append(summary)

            # Sections
            for section in report.sections:
                lines.append("")
                lines.append(f"--- {section.heading} ({section.count}) ---")
                for task in section.tasks:
                    lines.append(self._format_task_line(task))

        lines.append("")
        lines.append(separator)

        return "\n".join(lines)

    def send_email(self, report: DigestReport, recipient: str) -> str:
        """Send a digest report via email.

        Args:
            report: DigestReport to send.
            recipient: Email address to send the digest to.

        Returns:
            Gmail message ID of the sent email.

        Raises:
            DigestDeliveryError: If the email cannot be sent.
        """
        body = self.format_plain_text(report)
        subject = f"Daily Task Digest - {report.generated_at.strftime('%Y-%m-%d')}"

        message = MIMEText(body)
        message["to"] = recipient
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        try:
            service = self._get_gmail_service()
            result = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
            return result["id"]
        except HttpError as e:
            raise DigestDeliveryError(str(e)) from e

    def generate_and_send(
        self,
        recipient: Optional[str] = None,
        list_id: Optional[str] = None,
    ) -> DeliveryResult:
        """Generate a digest report and optionally send it via email.

        This is the main entry point. It:
        1. Builds the digest report from pending tasks
        2. Formats the report as plain text
        3. Optionally sends it via email if a recipient is provided

        Args:
            recipient: Email address to send digest to. If None,
                only plain text output is generated.
            list_id: Task list ID to report on. Uses default list if not specified.

        Returns:
            DeliveryResult with plain text output and email status.
        """
        result = DeliveryResult()

        # Build report
        try:
            report = self.build_report(list_id)
        except DigestBuildError as e:
            result.add_error(f"Build failed: {e.reason}")
            return result

        # Format plain text (always)
        result.plain_text_output = self.format_plain_text(report)

        # Send email (optional)
        if recipient:
            result.email_recipient = recipient
            try:
                message_id = self.send_email(report, recipient)
                result.email_sent = True
                result.email_message_id = message_id
            except DigestDeliveryError as e:
                result.add_error(f"Email delivery failed: {e.reason}")

        return result
