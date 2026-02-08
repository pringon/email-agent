"""CompletionChecker for detecting task completion via Sent Mail."""

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Iterator, Optional

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from src.fetcher.body_parser import extract_email_address
from src.fetcher.gmail_auth import GmailAuthenticator
from src.tasks import TaskManager

from .exceptions import SentMailAccessError
from .models import CompletionResult, SentEmail


class CompletionChecker:
    """Detects task completion by monitoring Sent Mail for replies.

    Scans the user's Sent Mail for outgoing messages, matches their
    thread IDs against existing tasks, and marks matching tasks as
    complete.

    The assumption is: if the user replied to an email thread that
    generated tasks, those tasks are considered handled.

    Example usage:
        checker = CompletionChecker()
        result = checker.check_for_completions()
        print(f"Completed {result.total_completed} tasks")

    With custom lookback:
        since = datetime.now() - timedelta(hours=1)
        result = checker.check_for_completions(since=since)
    """

    # Default lookback period for checking sent emails
    DEFAULT_LOOKBACK_HOURS = 24

    def __init__(
        self,
        authenticator: Optional[GmailAuthenticator] = None,
        task_manager: Optional[TaskManager] = None,
        gmail_service: Optional[Resource] = None,
    ):
        """Initialize the CompletionChecker.

        Args:
            authenticator: GmailAuthenticator for Gmail API access.
                Created with defaults if not provided.
            task_manager: TaskManager for finding and completing tasks.
                Created with defaults if not provided.
            gmail_service: Pre-configured Gmail API service for testing.
                Takes precedence over authenticator.
        """
        self._authenticator = authenticator
        self._task_manager = task_manager
        self._gmail_service = gmail_service

    def _get_gmail_service(self) -> Resource:
        """Get Gmail API service, creating if needed."""
        if self._gmail_service is None:
            if self._authenticator is None:
                self._authenticator = GmailAuthenticator()
            self._gmail_service = self._authenticator.get_service()
        return self._gmail_service

    def _get_task_manager(self) -> TaskManager:
        """Get TaskManager, creating if needed."""
        if self._task_manager is None:
            self._task_manager = TaskManager()
        return self._task_manager

    def _parse_sent_message(self, message: dict) -> SentEmail:
        """Parse Gmail API message into SentEmail object.

        Args:
            message: Full Gmail message from API (format='metadata').

        Returns:
            SentEmail object with relevant fields.
        """
        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        # Build header lookup
        header_map = {h["name"].lower(): h["value"] for h in headers}

        # Extract recipient
        recipient_raw = header_map.get("to", "")
        _, recipient_email = extract_email_address(recipient_raw)

        # Parse date
        date_str = header_map.get("date", "")
        try:
            date = parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            # Fallback to internal timestamp
            internal_date = message.get("internalDate", "0")
            date = datetime.fromtimestamp(int(internal_date) / 1000)

        return SentEmail(
            id=message["id"],
            thread_id=message["threadId"],
            subject=header_map.get("subject", "(No Subject)"),
            recipient=recipient_email,
            date=date,
            snippet=message.get("snippet", ""),
        )

    def fetch_sent_emails(
        self,
        since: Optional[datetime] = None,
        max_results: int = 100,
    ) -> Iterator[SentEmail]:
        """Fetch sent emails from Gmail.

        Args:
            since: Only fetch emails sent after this time.
                Defaults to 24 hours ago.
            max_results: Maximum number of emails to fetch.

        Yields:
            SentEmail objects for each sent message.

        Raises:
            SentMailAccessError: If unable to access Sent Mail.
        """
        if since is None:
            since = datetime.now() - timedelta(hours=self.DEFAULT_LOOKBACK_HOURS)

        # Build Gmail search query for sent mail after date
        # Gmail uses epoch seconds for after: filter
        after_timestamp = int(since.timestamp())
        query = f"in:sent after:{after_timestamp}"

        try:
            service = self._get_gmail_service()

            # List sent messages
            results = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=max_results,
                )
                .execute()
            )

            messages = results.get("messages", [])

            for msg_ref in messages:
                # Fetch message with metadata (headers only, not full body)
                message = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_ref["id"],
                        format="metadata",
                        metadataHeaders=["To", "Subject", "Date"],
                    )
                    .execute()
                )

                yield self._parse_sent_message(message)

        except HttpError as e:
            raise SentMailAccessError(str(e)) from e

    def get_thread_ids_with_tasks(
        self,
        include_completed: bool = False,
    ) -> set[str]:
        """Get all thread IDs that have associated tasks.

        Args:
            include_completed: Whether to include threads with
                only completed tasks.

        Returns:
            Set of Gmail thread IDs.
        """
        task_manager = self._get_task_manager()
        thread_ids = set()

        for task in task_manager.list_tasks(show_completed=include_completed):
            if task.source_thread_id:
                thread_ids.add(task.source_thread_id)

        return thread_ids

    def check_for_completions(
        self,
        since: Optional[datetime] = None,
        max_results: int = 100,
    ) -> CompletionResult:
        """Scan Sent Mail and complete matching tasks.

        This is the main entry point. It:
        1. Fetches recent sent emails
        2. Gets thread IDs with open tasks
        3. For each sent email in a matching thread, completes tasks

        Args:
            since: Only check emails sent after this time.
                Defaults to 24 hours ago.
            max_results: Maximum number of sent emails to check.

        Returns:
            CompletionResult with details of what was processed.
        """
        result = CompletionResult()
        task_manager = self._get_task_manager()

        # Get threads that have open tasks
        try:
            threads_with_tasks = self.get_thread_ids_with_tasks(include_completed=False)
        except Exception as e:
            result.add_error(f"Failed to get threads with tasks: {e}")
            return result

        if not threads_with_tasks:
            # No open tasks, nothing to check
            return result

        # Track which threads we've already processed
        processed_threads: set[str] = set()

        # Scan sent emails
        try:
            for sent_email in self.fetch_sent_emails(since=since, max_results=max_results):
                result.sent_emails_scanned += 1

                # Skip if already processed this thread
                if sent_email.thread_id in processed_threads:
                    continue

                # Check if this thread has tasks
                if sent_email.thread_id in threads_with_tasks:
                    try:
                        completed_tasks = task_manager.complete_tasks_for_thread(
                            sent_email.thread_id
                        )
                        task_ids = [t.id for t in completed_tasks if t.id]
                        result.add_completed_tasks(sent_email.thread_id, task_ids)
                    except Exception as e:
                        result.add_error(
                            f"Failed to complete tasks for thread {sent_email.thread_id}: {e}"
                        )

                processed_threads.add(sent_email.thread_id)

        except SentMailAccessError as e:
            result.add_error(str(e))

        return result

    def check_thread(self, thread_id: str) -> list[str]:
        """Check and complete tasks for a specific thread.

        Useful for targeted completion when you know a reply was sent.

        Args:
            thread_id: Gmail thread ID to check.

        Returns:
            List of task IDs that were completed.
        """
        task_manager = self._get_task_manager()
        completed_tasks = task_manager.complete_tasks_for_thread(thread_id)
        return [t.id for t in completed_tasks if t.id]
