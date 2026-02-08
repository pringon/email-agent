"""Unit tests for the CompletionChecker module."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from src.completion import (
    CompletionChecker,
    CompletionError,
    CompletionResult,
    SentEmail,
    SentMailAccessError,
)
from src.tasks import Task, TaskStatus


# ==================== SentEmail Model Tests ====================


class TestSentEmail:
    """Tests for SentEmail dataclass."""

    def test_create_sent_email(self):
        """Test creating a SentEmail instance."""
        now = datetime.now()
        email = SentEmail(
            id="msg123",
            thread_id="thread456",
            subject="Re: Test Subject",
            recipient="recipient@example.com",
            date=now,
            snippet="This is a reply...",
        )
        assert email.id == "msg123"
        assert email.thread_id == "thread456"
        assert email.subject == "Re: Test Subject"
        assert email.recipient == "recipient@example.com"
        assert email.date == now
        assert email.snippet == "This is a reply..."

    def test_sent_email_default_snippet(self):
        """Test that snippet defaults to empty string."""
        email = SentEmail(
            id="msg123",
            thread_id="thread456",
            subject="Subject",
            recipient="test@example.com",
            date=datetime.now(),
        )
        assert email.snippet == ""

    def test_sent_email_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        email = SentEmail(
            id="msg123",
            thread_id="thread456",
            subject="Test",
            recipient="test@example.com",
            date=now,
            snippet="Preview",
        )
        data = email.to_dict()
        assert data["id"] == "msg123"
        assert data["thread_id"] == "thread456"
        assert data["date"] == "2024-01-15T10:30:00"

    def test_sent_email_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "msg123",
            "thread_id": "thread456",
            "subject": "Test",
            "recipient": "test@example.com",
            "date": "2024-01-15T10:30:00",
            "snippet": "Preview",
        }
        email = SentEmail.from_dict(data)
        assert email.id == "msg123"
        assert email.thread_id == "thread456"
        assert email.date == datetime(2024, 1, 15, 10, 30, 0)

    def test_sent_email_roundtrip(self):
        """Test serialization roundtrip."""
        original = SentEmail(
            id="msg123",
            thread_id="thread456",
            subject="Test",
            recipient="test@example.com",
            date=datetime(2024, 1, 15, 10, 30, 0),
            snippet="Preview",
        )
        restored = SentEmail.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.thread_id == original.thread_id
        assert restored.subject == original.subject
        assert restored.date == original.date


# ==================== CompletionResult Tests ====================


class TestCompletionResult:
    """Tests for CompletionResult dataclass."""

    def test_create_default_result(self):
        """Test creating result with defaults."""
        result = CompletionResult()
        assert result.sent_emails_scanned == 0
        assert result.threads_matched == 0
        assert result.tasks_completed == []
        assert result.thread_task_map == {}
        assert result.checked_at is not None
        assert result.errors == []

    def test_result_total_completed(self):
        """Test total_completed property."""
        result = CompletionResult(
            tasks_completed=["task1", "task2", "task3"]
        )
        assert result.total_completed == 3

    def test_add_completed_tasks(self):
        """Test adding completed tasks for a thread."""
        result = CompletionResult()
        result.add_completed_tasks("thread1", ["task1", "task2"])

        assert result.threads_matched == 1
        assert result.tasks_completed == ["task1", "task2"]
        assert result.thread_task_map == {"thread1": ["task1", "task2"]}

    def test_add_completed_tasks_multiple_threads(self):
        """Test adding completed tasks for multiple threads."""
        result = CompletionResult()
        result.add_completed_tasks("thread1", ["task1"])
        result.add_completed_tasks("thread2", ["task2", "task3"])

        assert result.threads_matched == 2
        assert result.total_completed == 3
        assert "thread1" in result.thread_task_map
        assert "thread2" in result.thread_task_map

    def test_add_completed_tasks_empty_list(self):
        """Test that empty task list doesn't increment counters."""
        result = CompletionResult()
        result.add_completed_tasks("thread1", [])

        assert result.threads_matched == 0
        assert result.tasks_completed == []
        assert result.thread_task_map == {}

    def test_add_error(self):
        """Test adding errors."""
        result = CompletionResult()
        result.add_error("Something went wrong")
        result.add_error("Another error")

        assert len(result.errors) == 2
        assert "Something went wrong" in result.errors

    def test_result_to_dict(self):
        """Test serialization to dictionary."""
        result = CompletionResult(
            sent_emails_scanned=10,
            threads_matched=2,
            tasks_completed=["t1", "t2"],
            thread_task_map={"thread1": ["t1"], "thread2": ["t2"]},
        )
        data = result.to_dict()
        assert data["sent_emails_scanned"] == 10
        assert data["threads_matched"] == 2
        assert len(data["tasks_completed"]) == 2

    def test_result_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "sent_emails_scanned": 10,
            "threads_matched": 2,
            "tasks_completed": ["t1", "t2"],
            "thread_task_map": {"thread1": ["t1"]},
            "checked_at": "2024-01-15T10:30:00",
            "errors": ["error1"],
        }
        result = CompletionResult.from_dict(data)
        assert result.sent_emails_scanned == 10
        assert result.total_completed == 2
        assert len(result.errors) == 1


# ==================== Exception Tests ====================


class TestExceptions:
    """Tests for completion module exceptions."""

    def test_completion_error_is_exception(self):
        """Test that CompletionError is an Exception."""
        assert issubclass(CompletionError, Exception)

    def test_sent_mail_access_error(self):
        """Test SentMailAccessError message formatting."""
        error = SentMailAccessError("Permission denied")
        assert "Permission denied" in str(error)
        assert "Unable to access Sent Mail" in str(error)
        assert error.reason == "Permission denied"

    def test_sent_mail_access_error_inheritance(self):
        """Test that SentMailAccessError inherits from CompletionError."""
        assert issubclass(SentMailAccessError, CompletionError)


# ==================== CompletionChecker Tests ====================


class TestCompletionChecker:
    """Tests for CompletionChecker with mocked services."""

    @pytest.fixture
    def mock_gmail_service(self):
        """Create a mock Gmail API service."""
        return MagicMock()

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock TaskManager."""
        return MagicMock()

    @pytest.fixture
    def checker(self, mock_gmail_service, mock_task_manager):
        """Create a CompletionChecker with mocks."""
        return CompletionChecker(
            gmail_service=mock_gmail_service,
            task_manager=mock_task_manager,
        )

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        checker = CompletionChecker()
        assert checker._authenticator is None
        assert checker._task_manager is None
        assert checker._gmail_service is None

    def test_init_with_custom_values(self, mock_gmail_service, mock_task_manager):
        """Test initialization with custom values."""
        checker = CompletionChecker(
            gmail_service=mock_gmail_service,
            task_manager=mock_task_manager,
        )
        assert checker._gmail_service == mock_gmail_service
        assert checker._task_manager == mock_task_manager


class TestFetchSentEmails:
    """Tests for fetching sent emails."""

    @pytest.fixture
    def mock_gmail_service(self):
        """Create a mock Gmail API service."""
        return MagicMock()

    @pytest.fixture
    def checker(self, mock_gmail_service):
        """Create a CompletionChecker with mock Gmail service."""
        return CompletionChecker(gmail_service=mock_gmail_service)

    def test_fetch_sent_emails_empty(self, checker, mock_gmail_service):
        """Test fetching when no sent emails exist."""
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": []
        }

        emails = list(checker.fetch_sent_emails())
        assert emails == []

    def test_fetch_sent_emails_parses_messages(self, checker, mock_gmail_service):
        """Test that sent emails are parsed correctly."""
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "thread1"}]
        }
        mock_gmail_service.users().messages().get().execute.return_value = {
            "id": "msg1",
            "threadId": "thread1",
            "snippet": "Reply content",
            "internalDate": "1705315800000",
            "payload": {
                "headers": [
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Subject", "value": "Re: Test"},
                    {"name": "Date", "value": "Mon, 15 Jan 2024 10:30:00 +0000"},
                ]
            },
        }

        emails = list(checker.fetch_sent_emails())

        assert len(emails) == 1
        assert emails[0].id == "msg1"
        assert emails[0].thread_id == "thread1"
        assert emails[0].subject == "Re: Test"
        assert emails[0].recipient == "recipient@example.com"

    def test_fetch_sent_emails_uses_since_parameter(self, checker, mock_gmail_service):
        """Test that since parameter is used in query."""
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": []
        }

        since = datetime(2024, 1, 15, 0, 0, 0)
        list(checker.fetch_sent_emails(since=since))

        # Check the query includes the after: filter
        call_args = mock_gmail_service.users().messages().list.call_args
        query = call_args.kwargs.get("q") or call_args[1].get("q")
        assert "in:sent" in query
        assert "after:" in query

    def test_fetch_sent_emails_handles_api_error(self, checker, mock_gmail_service):
        """Test that API errors are wrapped in SentMailAccessError."""
        resp = MagicMock()
        resp.status = 403
        mock_gmail_service.users().messages().list().execute.side_effect = HttpError(
            resp=resp, content=b"Forbidden"
        )

        with pytest.raises(SentMailAccessError) as exc_info:
            list(checker.fetch_sent_emails())

        assert "Unable to access Sent Mail" in str(exc_info.value)

    def test_fetch_sent_emails_uses_metadata_format(self, checker, mock_gmail_service):
        """Test that messages are fetched with metadata format for efficiency."""
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "thread1"}]
        }
        mock_gmail_service.users().messages().get().execute.return_value = {
            "id": "msg1",
            "threadId": "thread1",
            "internalDate": "1705315800000",
            "payload": {"headers": []},
        }

        list(checker.fetch_sent_emails())

        call_args = mock_gmail_service.users().messages().get.call_args
        assert call_args.kwargs.get("format") == "metadata"


class TestGetThreadIdsWithTasks:
    """Tests for getting thread IDs with associated tasks."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock TaskManager."""
        return MagicMock()

    @pytest.fixture
    def checker(self, mock_task_manager):
        """Create a CompletionChecker with mock TaskManager."""
        return CompletionChecker(task_manager=mock_task_manager)

    def test_get_thread_ids_empty(self, checker, mock_task_manager):
        """Test when no tasks exist."""
        mock_task_manager.list_tasks.return_value = iter([])

        thread_ids = checker.get_thread_ids_with_tasks()

        assert thread_ids == set()

    def test_get_thread_ids_with_tasks(self, checker, mock_task_manager):
        """Test collecting thread IDs from tasks."""
        tasks = [
            Task(title="Task 1", id="t1", source_thread_id="thread1"),
            Task(title="Task 2", id="t2", source_thread_id="thread2"),
            Task(title="Task 3", id="t3", source_thread_id="thread1"),  # Same thread
        ]
        mock_task_manager.list_tasks.return_value = iter(tasks)

        thread_ids = checker.get_thread_ids_with_tasks()

        assert thread_ids == {"thread1", "thread2"}

    def test_get_thread_ids_skips_tasks_without_thread(self, checker, mock_task_manager):
        """Test that tasks without thread_id are skipped."""
        tasks = [
            Task(title="Task 1", id="t1", source_thread_id="thread1"),
            Task(title="Task 2", id="t2", source_thread_id=None),
        ]
        mock_task_manager.list_tasks.return_value = iter(tasks)

        thread_ids = checker.get_thread_ids_with_tasks()

        assert thread_ids == {"thread1"}


class TestCheckForCompletions:
    """Tests for the main check_for_completions method."""

    @pytest.fixture
    def mock_gmail_service(self):
        """Create a mock Gmail API service."""
        return MagicMock()

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock TaskManager."""
        return MagicMock()

    @pytest.fixture
    def checker(self, mock_gmail_service, mock_task_manager):
        """Create a CompletionChecker with mocks."""
        return CompletionChecker(
            gmail_service=mock_gmail_service,
            task_manager=mock_task_manager,
        )

    def test_check_completions_no_tasks(self, checker, mock_task_manager):
        """Test when no tasks exist."""
        mock_task_manager.list_tasks.return_value = iter([])

        result = checker.check_for_completions()

        assert result.sent_emails_scanned == 0
        assert result.total_completed == 0

    def test_check_completions_no_matching_threads(
        self, checker, mock_gmail_service, mock_task_manager
    ):
        """Test when sent emails don't match any task threads."""
        # Setup tasks with thread IDs
        tasks = [Task(title="Task", id="t1", source_thread_id="thread1")]
        mock_task_manager.list_tasks.return_value = iter(tasks)

        # Setup sent emails with different thread
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "other_thread"}]
        }
        mock_gmail_service.users().messages().get().execute.return_value = {
            "id": "msg1",
            "threadId": "other_thread",
            "internalDate": "1705315800000",
            "payload": {"headers": []},
        }

        result = checker.check_for_completions()

        assert result.sent_emails_scanned == 1
        assert result.total_completed == 0
        mock_task_manager.complete_tasks_for_thread.assert_not_called()

    def test_check_completions_completes_matching_tasks(
        self, checker, mock_gmail_service, mock_task_manager
    ):
        """Test that matching tasks are completed."""
        # Setup tasks
        tasks = [Task(title="Task", id="t1", source_thread_id="thread1")]
        mock_task_manager.list_tasks.return_value = iter(tasks)

        # Setup sent email matching the task's thread
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "thread1"}]
        }
        mock_gmail_service.users().messages().get().execute.return_value = {
            "id": "msg1",
            "threadId": "thread1",
            "internalDate": "1705315800000",
            "payload": {"headers": []},
        }

        # Setup completion result
        completed_task = Task(title="Task", id="t1", status=TaskStatus.COMPLETED)
        mock_task_manager.complete_tasks_for_thread.return_value = [completed_task]

        result = checker.check_for_completions()

        assert result.sent_emails_scanned == 1
        assert result.threads_matched == 1
        assert result.total_completed == 1
        assert "t1" in result.tasks_completed
        mock_task_manager.complete_tasks_for_thread.assert_called_once_with("thread1")

    def test_check_completions_deduplicates_threads(
        self, checker, mock_gmail_service, mock_task_manager
    ):
        """Test that multiple emails in same thread only complete once."""
        # Setup tasks
        tasks = [Task(title="Task", id="t1", source_thread_id="thread1")]
        mock_task_manager.list_tasks.return_value = iter(tasks)

        # Setup multiple sent emails in same thread
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [
                {"id": "msg1", "threadId": "thread1"},
                {"id": "msg2", "threadId": "thread1"},  # Same thread
            ]
        }
        # Return different messages for each get() call
        mock_gmail_service.users().messages().get().execute.side_effect = [
            {
                "id": "msg1",
                "threadId": "thread1",
                "internalDate": "1705315800000",
                "payload": {"headers": []},
            },
            {
                "id": "msg2",
                "threadId": "thread1",
                "internalDate": "1705316000000",
                "payload": {"headers": []},
            },
        ]

        completed_task = Task(title="Task", id="t1", status=TaskStatus.COMPLETED)
        mock_task_manager.complete_tasks_for_thread.return_value = [completed_task]

        result = checker.check_for_completions()

        assert result.sent_emails_scanned == 2
        assert result.threads_matched == 1  # Only one thread matched
        # complete_tasks_for_thread should only be called once
        mock_task_manager.complete_tasks_for_thread.assert_called_once()

    def test_check_completions_handles_completion_error(
        self, checker, mock_gmail_service, mock_task_manager
    ):
        """Test that errors during completion are recorded."""
        # Setup tasks
        tasks = [Task(title="Task", id="t1", source_thread_id="thread1")]
        mock_task_manager.list_tasks.return_value = iter(tasks)

        # Setup sent email
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "thread1"}]
        }
        mock_gmail_service.users().messages().get().execute.return_value = {
            "id": "msg1",
            "threadId": "thread1",
            "internalDate": "1705315800000",
            "payload": {"headers": []},
        }

        # Setup completion to fail
        mock_task_manager.complete_tasks_for_thread.side_effect = Exception("API error")

        result = checker.check_for_completions()

        assert result.sent_emails_scanned == 1
        assert result.total_completed == 0
        assert len(result.errors) == 1
        assert "thread1" in result.errors[0]


class TestCheckThread:
    """Tests for checking a specific thread."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock TaskManager."""
        return MagicMock()

    @pytest.fixture
    def checker(self, mock_task_manager):
        """Create a CompletionChecker with mock TaskManager."""
        return CompletionChecker(task_manager=mock_task_manager)

    def test_check_thread_completes_tasks(self, checker, mock_task_manager):
        """Test completing tasks for a specific thread."""
        completed_tasks = [
            Task(title="Task 1", id="t1", status=TaskStatus.COMPLETED),
            Task(title="Task 2", id="t2", status=TaskStatus.COMPLETED),
        ]
        mock_task_manager.complete_tasks_for_thread.return_value = completed_tasks

        task_ids = checker.check_thread("thread123")

        assert task_ids == ["t1", "t2"]
        mock_task_manager.complete_tasks_for_thread.assert_called_once_with("thread123")

    def test_check_thread_no_tasks(self, checker, mock_task_manager):
        """Test when thread has no associated tasks."""
        mock_task_manager.complete_tasks_for_thread.return_value = []

        task_ids = checker.check_thread("thread123")

        assert task_ids == []


class TestParseSentMessage:
    """Tests for parsing Gmail API messages."""

    @pytest.fixture
    def checker(self):
        """Create a CompletionChecker."""
        return CompletionChecker(gmail_service=MagicMock())

    def test_parse_with_full_headers(self, checker):
        """Test parsing message with all headers."""
        message = {
            "id": "msg123",
            "threadId": "thread456",
            "snippet": "Reply content here...",
            "payload": {
                "headers": [
                    {"name": "To", "value": "John Doe <john@example.com>"},
                    {"name": "Subject", "value": "Re: Important Meeting"},
                    {"name": "Date", "value": "Mon, 15 Jan 2024 10:30:00 +0000"},
                ]
            },
        }

        email = checker._parse_sent_message(message)

        assert email.id == "msg123"
        assert email.thread_id == "thread456"
        assert email.subject == "Re: Important Meeting"
        assert email.recipient == "john@example.com"
        assert email.snippet == "Reply content here..."

    def test_parse_with_missing_headers(self, checker):
        """Test parsing message with minimal headers."""
        message = {
            "id": "msg123",
            "threadId": "thread456",
            "internalDate": "1705315800000",
            "payload": {
                "headers": []
            },
        }

        email = checker._parse_sent_message(message)

        assert email.id == "msg123"
        assert email.thread_id == "thread456"
        assert email.subject == "(No Subject)"
        assert email.recipient == ""

    def test_parse_uses_internal_date_fallback(self, checker):
        """Test that internal date is used when Date header is invalid."""
        message = {
            "id": "msg123",
            "threadId": "thread456",
            "internalDate": "1705315800000",  # Jan 15, 2024
            "payload": {
                "headers": [
                    {"name": "Date", "value": "invalid-date"},
                ]
            },
        }

        email = checker._parse_sent_message(message)

        # Should use internalDate as fallback
        assert email.date.year == 2024
