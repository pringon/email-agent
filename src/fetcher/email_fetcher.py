"""Main EmailFetcher class for fetching emails from Gmail API."""

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Iterator, Optional

from googleapiclient.discovery import Resource

from .body_parser import extract_body, extract_email_address
from .gmail_auth import GmailAuthenticator
from .models import Email
from .state import InMemoryStateRepository, StateRepository


class EmailFetcher:
    """Fetches emails from Gmail and returns structured Email objects.

    The fetcher is designed for stateless cronjob operation:
    - Uses injectable StateRepository to track processed emails
    - Tracks by message ID (not thread) so replies are processed independently
    - Includes thread_id in Email objects for downstream context

    Example usage:
        fetcher = EmailFetcher()
        for email in fetcher.fetch_unread(max_results=10):
            print(f"Subject: {email.subject}")
            print(f"Thread: {email.thread_id}")

    With state tracking:
        state = InMemoryStateRepository()
        fetcher = EmailFetcher(state_repository=state)
        for email in fetcher.fetch_new_emails(max_results=10):
            # Process email...
            state.mark_processed(email.id)
    """

    def __init__(
        self,
        state_repository: Optional[StateRepository] = None,
        authenticator: Optional[GmailAuthenticator] = None,
        service: Optional[Resource] = None,
    ):
        """Initialize the EmailFetcher.

        Args:
            state_repository: Repository for tracking processed emails.
                Defaults to InMemoryStateRepository (all emails appear new).
            authenticator: Gmail authenticator instance.
                Defaults to GmailAuthenticator with default paths.
            service: Pre-built Gmail API service (for testing).
                If provided, authenticator is ignored.
        """
        self._state = state_repository or InMemoryStateRepository()
        self._auth = authenticator
        self._service = service

    def _get_service(self) -> Resource:
        """Get Gmail API service, creating if needed."""
        if self._service is None:
            if self._auth is None:
                self._auth = GmailAuthenticator()
            self._service = self._auth.get_service()
        return self._service

    def _parse_message(self, message: dict) -> Email:
        """Parse Gmail API message into Email object.

        Args:
            message: Full Gmail message from API (format='full')

        Returns:
            Structured Email object
        """
        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        # Build header lookup for efficiency
        header_map = {h["name"].lower(): h["value"] for h in headers}

        # Extract email addresses
        sender_raw = header_map.get("from", "")
        sender_name, sender_email = extract_email_address(sender_raw)

        recipient_raw = header_map.get("to", "")
        _, recipient_email = extract_email_address(recipient_raw)

        # Parse date
        date_str = header_map.get("date", "")
        try:
            date = parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            # Fallback to internal timestamp (milliseconds since epoch)
            internal_date = message.get("internalDate", "0")
            date = datetime.fromtimestamp(int(internal_date) / 1000)

        # Extract body content
        body, html_body = extract_body(payload)

        # Check labels
        labels = message.get("labelIds", [])
        is_unread = "UNREAD" in labels

        return Email(
            id=message["id"],
            thread_id=message["threadId"],
            subject=header_map.get("subject", "(No Subject)"),
            sender=sender_name,
            sender_email=sender_email,
            recipient=recipient_email,
            date=date,
            body=body,
            html_body=html_body,
            snippet=message.get("snippet", ""),
            labels=labels,
            is_unread=is_unread,
        )

    def fetch_unread(self, max_results: int = 50) -> Iterator[Email]:
        """Fetch unread emails from inbox.

        Uses Gmail search to find unread messages in INBOX.

        Args:
            max_results: Maximum number of emails to fetch

        Yields:
            Email objects for each unread message
        """
        service = self._get_service()

        # List unread messages in inbox
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                q="is:unread in:inbox",
                maxResults=max_results,
            )
            .execute()
        )

        messages = results.get("messages", [])

        for msg_ref in messages:
            # Fetch full message details
            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg_ref["id"],
                    format="full",
                )
                .execute()
            )

            yield self._parse_message(message)

    def fetch_new_emails(self, max_results: int = 50) -> Iterator[Email]:
        """Fetch emails not yet processed (by message ID).

        Filters fetch_unread results through the state repository
        to skip already-processed messages.

        Note: Caller is responsible for calling state.mark_processed()
        after successfully handling each email.

        Args:
            max_results: Maximum number of unread emails to check

        Yields:
            Email objects for unread, unprocessed messages
        """
        for email in self.fetch_unread(max_results):
            if not self._state.is_processed(email.id):
                yield email

    def fetch_by_id(self, message_id: str) -> Email:
        """Fetch a specific email by message ID.

        Args:
            message_id: Gmail message ID

        Returns:
            Email object for the specified message

        Raises:
            googleapiclient.errors.HttpError: If message not found
        """
        service = self._get_service()

        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

        return self._parse_message(message)

    @property
    def state(self) -> StateRepository:
        """Access the state repository."""
        return self._state
