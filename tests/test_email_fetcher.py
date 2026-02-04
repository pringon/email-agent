"""Unit tests for the EmailFetcher module."""

import base64
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.fetcher import Email, EmailFetcher, InMemoryStateRepository
from src.fetcher.body_parser import (
    decode_base64,
    extract_body,
    extract_email_address,
    html_to_plain_text,
)


class TestDecodeBase64:
    """Tests for base64 decoding."""

    def test_decode_simple_text(self):
        """Test decoding simple ASCII text."""
        text = "Hello, World!"
        encoded = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
        assert decode_base64(encoded) == text

    def test_decode_with_padding(self):
        """Test decoding handles missing padding."""
        text = "Test"
        encoded = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
        assert decode_base64(encoded) == text

    def test_decode_unicode(self):
        """Test decoding UTF-8 content."""
        text = "Héllo Wörld 🌍"
        encoded = base64.urlsafe_b64encode(text.encode()).decode()
        assert decode_base64(encoded) == text


class TestExtractEmailAddress:
    """Tests for email address extraction."""

    def test_name_and_email(self):
        """Test extracting name and email from standard format."""
        name, email = extract_email_address("John Doe <john@example.com>")
        assert name == "John Doe"
        assert email == "john@example.com"

    def test_quoted_name(self):
        """Test extracting quoted name."""
        name, email = extract_email_address('"John Doe" <john@example.com>')
        assert name == "John Doe"
        assert email == "john@example.com"

    def test_email_only_brackets(self):
        """Test email with brackets but no name."""
        name, email = extract_email_address("<john@example.com>")
        assert name == "john@example.com"
        assert email == "john@example.com"

    def test_plain_email(self):
        """Test plain email address without brackets."""
        name, email = extract_email_address("john@example.com")
        assert name == "john@example.com"
        assert email == "john@example.com"

    def test_whitespace_handling(self):
        """Test handling of extra whitespace."""
        name, email = extract_email_address("  John Doe  <john@example.com>  ")
        assert name == "John Doe"
        assert email == "john@example.com"


class TestHtmlToPlainText:
    """Tests for HTML to plain text conversion."""

    def test_simple_html(self):
        """Test converting simple HTML."""
        html = "<p>Hello</p><p>World</p>"
        result = html_to_plain_text(html)
        assert "Hello" in result
        assert "World" in result

    def test_strips_script_tags(self):
        """Test that script content is removed."""
        html = "<p>Text</p><script>alert('hi')</script><p>More</p>"
        result = html_to_plain_text(html)
        assert "alert" not in result
        assert "Text" in result
        assert "More" in result

    def test_strips_style_tags(self):
        """Test that style content is removed."""
        html = "<style>.class { color: red; }</style><p>Content</p>"
        result = html_to_plain_text(html)
        assert "color" not in result
        assert "Content" in result

    def test_preserves_line_breaks(self):
        """Test that block elements create line breaks."""
        html = "<div>Line 1</div><div>Line 2</div>"
        result = html_to_plain_text(html)
        assert "Line 1" in result
        assert "Line 2" in result


class TestExtractBody:
    """Tests for email body extraction."""

    def test_simple_text_body(self):
        """Test extracting plain text body."""
        text = "Hello, this is a test email."
        encoded = base64.urlsafe_b64encode(text.encode()).decode()
        payload = {
            "mimeType": "text/plain",
            "body": {"data": encoded},
        }
        plain, html = extract_body(payload)
        assert plain == text
        assert html is None

    def test_simple_html_body(self):
        """Test extracting HTML body with text fallback."""
        html_content = "<p>Hello, this is a test email.</p>"
        encoded = base64.urlsafe_b64encode(html_content.encode()).decode()
        payload = {
            "mimeType": "text/html",
            "body": {"data": encoded},
        }
        plain, html = extract_body(payload)
        assert html == html_content
        assert "Hello" in plain  # Converted from HTML

    def test_multipart_body(self):
        """Test extracting from multipart message."""
        text = "Plain text version"
        html = "<p>HTML version</p>"
        text_encoded = base64.urlsafe_b64encode(text.encode()).decode()
        html_encoded = base64.urlsafe_b64encode(html.encode()).decode()

        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": text_encoded}},
                {"mimeType": "text/html", "body": {"data": html_encoded}},
            ],
        }
        plain, html_body = extract_body(payload)
        assert plain == text
        assert html_body == html

    def test_nested_multipart(self):
        """Test extracting from nested multipart structure."""
        text = "Nested plain text"
        text_encoded = base64.urlsafe_b64encode(text.encode()).decode()

        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": text_encoded}},
                    ],
                },
                {
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "abc123"},
                },
            ],
        }
        plain, html = extract_body(payload)
        assert plain == text


class TestInMemoryStateRepository:
    """Tests for InMemoryStateRepository."""

    def test_initially_empty(self):
        """Test that repository starts empty."""
        repo = InMemoryStateRepository()
        assert repo.get_processed_ids() == set()
        assert not repo.is_processed("msg123")

    def test_mark_processed(self):
        """Test marking messages as processed."""
        repo = InMemoryStateRepository()
        repo.mark_processed("msg123")
        assert repo.is_processed("msg123")
        assert "msg123" in repo.get_processed_ids()

    def test_multiple_messages(self):
        """Test tracking multiple messages."""
        repo = InMemoryStateRepository()
        repo.mark_processed("msg1")
        repo.mark_processed("msg2")
        repo.mark_processed("msg3")

        assert repo.is_processed("msg1")
        assert repo.is_processed("msg2")
        assert repo.is_processed("msg3")
        assert not repo.is_processed("msg4")
        assert repo.get_processed_ids() == {"msg1", "msg2", "msg3"}

    def test_clear(self):
        """Test clearing processed IDs."""
        repo = InMemoryStateRepository()
        repo.mark_processed("msg1")
        repo.clear()
        assert not repo.is_processed("msg1")
        assert repo.get_processed_ids() == set()


class TestEmailModel:
    """Tests for Email dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        email = Email(
            id="msg123",
            thread_id="thread456",
            subject="Test Subject",
            sender="John Doe",
            sender_email="john@example.com",
            recipient="jane@example.com",
            date=datetime(2024, 1, 15, 10, 30, 0),
            body="Test body",
            html_body="<p>Test body</p>",
            snippet="Test snippet",
            labels=["INBOX", "UNREAD"],
            is_unread=True,
        )

        data = email.to_dict()
        assert data["id"] == "msg123"
        assert data["thread_id"] == "thread456"
        assert data["subject"] == "Test Subject"
        assert data["date"] == "2024-01-15T10:30:00"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "msg123",
            "thread_id": "thread456",
            "subject": "Test Subject",
            "sender": "John Doe",
            "sender_email": "john@example.com",
            "recipient": "jane@example.com",
            "date": "2024-01-15T10:30:00",
            "body": "Test body",
            "html_body": "<p>Test body</p>",
            "snippet": "Test snippet",
            "labels": ["INBOX", "UNREAD"],
            "is_unread": True,
        }

        email = Email.from_dict(data)
        assert email.id == "msg123"
        assert email.thread_id == "thread456"
        assert email.date == datetime(2024, 1, 15, 10, 30, 0)

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = Email(
            id="msg123",
            thread_id="thread456",
            subject="Test Subject",
            sender="John Doe",
            sender_email="john@example.com",
            recipient="jane@example.com",
            date=datetime(2024, 1, 15, 10, 30, 0),
            body="Test body",
        )

        restored = Email.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.thread_id == original.thread_id
        assert restored.subject == original.subject
        assert restored.date == original.date


class TestEmailFetcher:
    """Tests for EmailFetcher with mocked Gmail service."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock Gmail service."""
        service = MagicMock()
        return service

    @pytest.fixture
    def sample_message(self):
        """Create a sample Gmail message response."""
        body_text = "This is the email body content."
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        return {
            "id": "msg123",
            "threadId": "thread456",
            "snippet": "This is the email body...",
            "internalDate": "1705312200000",  # 2024-01-15 10:30:00 UTC
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "John Doe <john@example.com>"},
                    {"name": "To", "value": "jane@example.com"},
                    {"name": "Subject", "value": "Test Email Subject"},
                    {"name": "Date", "value": "Mon, 15 Jan 2024 10:30:00 +0000"},
                ],
                "body": {"data": encoded_body},
            },
        }

    def test_fetch_unread_returns_emails(self, mock_service, sample_message):
        """Test that fetch_unread returns Email objects."""
        # Setup mock responses
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg123", "threadId": "thread456"}]
        }
        mock_service.users().messages().get().execute.return_value = sample_message

        fetcher = EmailFetcher(service=mock_service)
        emails = list(fetcher.fetch_unread(max_results=10))

        assert len(emails) == 1
        assert emails[0].id == "msg123"
        assert emails[0].thread_id == "thread456"
        assert emails[0].subject == "Test Email Subject"
        assert emails[0].sender == "John Doe"
        assert emails[0].sender_email == "john@example.com"
        assert emails[0].is_unread is True

    def test_fetch_unread_empty(self, mock_service):
        """Test fetch_unread with no messages."""
        mock_service.users().messages().list().execute.return_value = {"messages": []}

        fetcher = EmailFetcher(service=mock_service)
        emails = list(fetcher.fetch_unread())

        assert len(emails) == 0

    def test_fetch_new_emails_filters_processed(self, mock_service, sample_message):
        """Test that fetch_new_emails skips processed messages."""
        mock_service.users().messages().list().execute.return_value = {
            "messages": [
                {"id": "msg1", "threadId": "thread1"},
                {"id": "msg2", "threadId": "thread2"},
                {"id": "msg3", "threadId": "thread3"},
            ]
        }

        # Return different messages for different IDs
        def get_message(**kwargs):
            msg_id = kwargs.get("id", "msg1")
            msg = sample_message.copy()
            msg["id"] = msg_id
            return MagicMock(execute=MagicMock(return_value=msg))

        mock_service.users().messages().get = get_message

        # Pre-mark msg2 as processed
        state = InMemoryStateRepository()
        state.mark_processed("msg2")

        fetcher = EmailFetcher(state_repository=state, service=mock_service)
        emails = list(fetcher.fetch_new_emails())

        # Should return msg1 and msg3 but not msg2
        ids = [e.id for e in emails]
        assert "msg1" in ids
        assert "msg2" not in ids
        assert "msg3" in ids

    def test_fetch_by_id(self, mock_service, sample_message):
        """Test fetching a specific email by ID."""
        mock_service.users().messages().get().execute.return_value = sample_message

        fetcher = EmailFetcher(service=mock_service)
        email = fetcher.fetch_by_id("msg123")

        assert email.id == "msg123"
        assert email.subject == "Test Email Subject"

    def test_state_property(self):
        """Test accessing the state repository."""
        state = InMemoryStateRepository()
        fetcher = EmailFetcher(state_repository=state, service=MagicMock())

        assert fetcher.state is state

    def test_parse_date_fallback(self, mock_service, sample_message):
        """Test date parsing fallback to internalDate."""
        # Remove the Date header
        sample_message["payload"]["headers"] = [
            h for h in sample_message["payload"]["headers"] if h["name"] != "Date"
        ]

        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg123"}]
        }
        mock_service.users().messages().get().execute.return_value = sample_message

        fetcher = EmailFetcher(service=mock_service)
        emails = list(fetcher.fetch_unread())

        # Should still have a valid date from internalDate
        assert emails[0].date is not None
        assert isinstance(emails[0].date, datetime)


class TestEmailFetcherIntegration:
    """Integration-style tests for EmailFetcher initialization."""

    def test_default_initialization(self):
        """Test that EmailFetcher can be created with defaults."""
        # This doesn't make API calls, just tests initialization
        fetcher = EmailFetcher()
        assert isinstance(fetcher.state, InMemoryStateRepository)

    def test_custom_state_repository(self):
        """Test initialization with custom state repository."""
        state = InMemoryStateRepository()
        fetcher = EmailFetcher(state_repository=state)
        assert fetcher.state is state
