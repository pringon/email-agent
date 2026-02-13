"""Unit tests for the DigestReporter module."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from src.digest import (
    DeliveryResult,
    DigestBuildError,
    DigestDeliveryError,
    DigestError,
    DigestReport,
    DigestReporter,
    DigestSection,
)
from src.tasks.models import Task, TaskStatus


# ==================== DigestSection Model Tests ====================


class TestDigestSection:
    """Tests for DigestSection dataclass."""

    def test_create_section(self):
        """Test creating a DigestSection with heading and tasks."""
        task = Task(title="Test task")
        section = DigestSection(heading="Overdue", tasks=[task])

        assert section.heading == "Overdue"
        assert len(section.tasks) == 1
        assert section.tasks[0].title == "Test task"

    def test_create_empty_section(self):
        """Test creating a section with no tasks."""
        section = DigestSection(heading="Due Today")

        assert section.heading == "Due Today"
        assert section.tasks == []

    def test_count_property(self):
        """Test that count returns the number of tasks."""
        tasks = [Task(title="Task 1"), Task(title="Task 2"), Task(title="Task 3")]
        section = DigestSection(heading="Test", tasks=tasks)

        assert section.count == 3

    def test_count_empty(self):
        """Test count for empty section."""
        section = DigestSection(heading="Empty")

        assert section.count == 0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        task = Task(title="Test task", status=TaskStatus.NEEDS_ACTION)
        section = DigestSection(heading="Overdue", tasks=[task])

        data = section.to_dict()

        assert data["heading"] == "Overdue"
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["title"] == "Test task"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "heading": "Due Today",
            "tasks": [{"title": "Task 1", "status": "needsAction"}],
        }

        section = DigestSection.from_dict(data)

        assert section.heading == "Due Today"
        assert len(section.tasks) == 1
        assert section.tasks[0].title == "Task 1"

    def test_roundtrip(self):
        """Test serialization/deserialization roundtrip."""
        original = DigestSection(
            heading="Overdue",
            tasks=[Task(title="Task 1"), Task(title="Task 2")],
        )

        restored = DigestSection.from_dict(original.to_dict())

        assert restored.heading == original.heading
        assert restored.count == original.count
        assert restored.tasks[0].title == original.tasks[0].title
        assert restored.tasks[1].title == original.tasks[1].title


# ==================== DigestReport Model Tests ====================


class TestDigestReport:
    """Tests for DigestReport dataclass."""

    def test_create_default_report(self):
        """Test creating a report with defaults."""
        report = DigestReport()

        assert report.generated_at is not None
        assert report.sections == []
        assert report.total_pending == 0
        assert report.total_overdue == 0
        assert report.task_list_name == ""

    def test_create_report_with_data(self):
        """Test creating a report with sections and stats."""
        section = DigestSection(heading="Overdue", tasks=[Task(title="Task 1")])
        now = datetime(2026, 2, 10, 9, 0, 0)

        report = DigestReport(
            generated_at=now,
            sections=[section],
            total_pending=1,
            total_overdue=1,
            task_list_name="Email Tasks",
        )

        assert report.generated_at == now
        assert len(report.sections) == 1
        assert report.total_pending == 1
        assert report.total_overdue == 1
        assert report.task_list_name == "Email Tasks"

    def test_is_empty_true(self):
        """Test is_empty when no pending tasks."""
        report = DigestReport(total_pending=0)

        assert report.is_empty is True

    def test_is_empty_false(self):
        """Test is_empty when tasks exist."""
        report = DigestReport(total_pending=3)

        assert report.is_empty is False

    def test_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime(2026, 2, 10, 9, 0, 0)
        section = DigestSection(heading="Overdue", tasks=[Task(title="Task 1")])
        report = DigestReport(
            generated_at=now,
            sections=[section],
            total_pending=1,
            total_overdue=1,
            task_list_name="Email Tasks",
        )

        data = report.to_dict()

        assert data["generated_at"] == "2026-02-10T09:00:00"
        assert len(data["sections"]) == 1
        assert data["total_pending"] == 1
        assert data["total_overdue"] == 1
        assert data["task_list_name"] == "Email Tasks"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "generated_at": "2026-02-10T09:00:00",
            "sections": [
                {"heading": "Overdue", "tasks": [{"title": "Task 1", "status": "needsAction"}]},
            ],
            "total_pending": 1,
            "total_overdue": 1,
            "task_list_name": "Email Tasks",
        }

        report = DigestReport.from_dict(data)

        assert report.generated_at == datetime(2026, 2, 10, 9, 0, 0)
        assert len(report.sections) == 1
        assert report.total_pending == 1
        assert report.task_list_name == "Email Tasks"

    def test_roundtrip(self):
        """Test full serialize/deserialize roundtrip."""
        now = datetime(2026, 2, 10, 9, 0, 0)
        original = DigestReport(
            generated_at=now,
            sections=[DigestSection(heading="Overdue", tasks=[Task(title="Task 1")])],
            total_pending=1,
            total_overdue=1,
            task_list_name="Email Tasks",
        )

        restored = DigestReport.from_dict(original.to_dict())

        assert restored.generated_at == original.generated_at
        assert restored.total_pending == original.total_pending
        assert restored.total_overdue == original.total_overdue
        assert restored.task_list_name == original.task_list_name
        assert len(restored.sections) == len(original.sections)


# ==================== DeliveryResult Model Tests ====================


class TestDeliveryResult:
    """Tests for DeliveryResult dataclass."""

    def test_create_default_result(self):
        """Test creating a result with defaults."""
        result = DeliveryResult()

        assert result.delivered_at is not None
        assert result.plain_text_output == ""
        assert result.email_sent is False
        assert result.email_recipient == ""
        assert result.email_message_id is None
        assert result.errors == []

    def test_has_errors_false(self):
        """Test has_errors when no errors."""
        result = DeliveryResult()

        assert result.has_errors is False

    def test_has_errors_true(self):
        """Test has_errors when errors exist."""
        result = DeliveryResult(errors=["Something went wrong"])

        assert result.has_errors is True

    def test_add_error(self):
        """Test adding errors."""
        result = DeliveryResult()
        result.add_error("Error 1")
        result.add_error("Error 2")

        assert len(result.errors) == 2
        assert result.errors[0] == "Error 1"
        assert result.errors[1] == "Error 2"
        assert result.has_errors is True

    def test_email_sent_fields(self):
        """Test result with email delivery fields."""
        result = DeliveryResult(
            email_sent=True,
            email_recipient="user@example.com",
            email_message_id="msg123",
        )

        assert result.email_sent is True
        assert result.email_recipient == "user@example.com"
        assert result.email_message_id == "msg123"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime(2026, 2, 10, 9, 0, 0)
        result = DeliveryResult(
            delivered_at=now,
            plain_text_output="digest text",
            email_sent=True,
            email_recipient="user@example.com",
            email_message_id="msg123",
            errors=["warning"],
        )

        data = result.to_dict()

        assert data["delivered_at"] == "2026-02-10T09:00:00"
        assert data["plain_text_output"] == "digest text"
        assert data["email_sent"] is True
        assert data["email_recipient"] == "user@example.com"
        assert data["email_message_id"] == "msg123"
        assert data["errors"] == ["warning"]

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "delivered_at": "2026-02-10T09:00:00",
            "plain_text_output": "digest text",
            "email_sent": True,
            "email_recipient": "user@example.com",
            "email_message_id": "msg123",
            "errors": [],
        }

        result = DeliveryResult.from_dict(data)

        assert result.delivered_at == datetime(2026, 2, 10, 9, 0, 0)
        assert result.plain_text_output == "digest text"
        assert result.email_sent is True
        assert result.email_recipient == "user@example.com"
        assert result.email_message_id == "msg123"

    def test_roundtrip(self):
        """Test full serialize/deserialize roundtrip."""
        now = datetime(2026, 2, 10, 9, 0, 0)
        original = DeliveryResult(
            delivered_at=now,
            plain_text_output="text",
            email_sent=True,
            email_recipient="user@example.com",
            email_message_id="msg123",
            errors=["err1"],
        )

        restored = DeliveryResult.from_dict(original.to_dict())

        assert restored.delivered_at == original.delivered_at
        assert restored.plain_text_output == original.plain_text_output
        assert restored.email_sent == original.email_sent
        assert restored.email_recipient == original.email_recipient
        assert restored.email_message_id == original.email_message_id
        assert restored.errors == original.errors


# ==================== Exception Tests ====================


class TestExceptions:
    """Tests for digest module exceptions."""

    def test_digest_error_is_exception(self):
        """Test DigestError is a base Exception."""
        error = DigestError("test")
        assert isinstance(error, Exception)

    def test_digest_build_error(self):
        """Test DigestBuildError message formatting."""
        error = DigestBuildError("API unavailable")

        assert error.reason == "API unavailable"
        assert "Failed to build digest report" in str(error)
        assert "API unavailable" in str(error)

    def test_digest_delivery_error(self):
        """Test DigestDeliveryError message formatting."""
        error = DigestDeliveryError("SMTP failure")

        assert error.reason == "SMTP failure"
        assert "Failed to deliver digest" in str(error)
        assert "SMTP failure" in str(error)

    def test_build_error_inherits_digest_error(self):
        """Test DigestBuildError is a DigestError."""
        error = DigestBuildError("test")
        assert isinstance(error, DigestError)

    def test_delivery_error_inherits_digest_error(self):
        """Test DigestDeliveryError is a DigestError."""
        error = DigestDeliveryError("test")
        assert isinstance(error, DigestError)


# ==================== DigestReporter Init Tests ====================


class TestDigestReporter:
    """Tests for DigestReporter initialization."""

    def test_init_with_defaults(self):
        """Test default initialization."""
        reporter = DigestReporter()

        assert reporter._task_manager is None
        assert reporter._authenticator is None
        assert reporter._gmail_service is None

    def test_init_with_dependencies(self):
        """Test initialization with injected dependencies."""
        mock_tm = MagicMock()
        mock_auth = MagicMock()
        mock_service = MagicMock()

        reporter = DigestReporter(
            task_manager=mock_tm,
            authenticator=mock_auth,
            gmail_service=mock_service,
        )

        assert reporter._task_manager is mock_tm
        assert reporter._authenticator is mock_auth
        assert reporter._gmail_service is mock_service

    def test_lazy_task_manager_creation(self):
        """Test TaskManager is not created until needed."""
        reporter = DigestReporter()
        assert reporter._task_manager is None


# ==================== Categorize Tasks Tests ====================


class TestCategorizeTasks:
    """Tests for task categorization by due date."""

    @pytest.fixture
    def reporter(self):
        """Create a DigestReporter instance."""
        return DigestReporter()

    def test_categorize_overdue(self, reporter):
        """Test tasks with past due dates go to Overdue."""
        yesterday = date.today() - timedelta(days=1)
        task = Task(title="Overdue task", due=yesterday)

        sections = reporter._categorize_tasks([task])

        assert len(sections) == 1
        assert sections[0].heading == "Overdue"
        assert sections[0].count == 1

    def test_categorize_due_today(self, reporter):
        """Test tasks due today go to Due Today."""
        today = date.today()
        task = Task(title="Today's task", due=today)

        sections = reporter._categorize_tasks([task])

        assert len(sections) == 1
        assert sections[0].heading == "Due Today"
        assert sections[0].count == 1

    def test_categorize_due_this_week(self, reporter):
        """Test tasks due within 7 days go to Due This Week."""
        in_3_days = date.today() + timedelta(days=3)
        task = Task(title="This week task", due=in_3_days)

        sections = reporter._categorize_tasks([task])

        assert len(sections) == 1
        assert sections[0].heading == "Due This Week"
        assert sections[0].count == 1

    def test_categorize_due_later(self, reporter):
        """Test tasks due beyond 7 days go to Due Later."""
        in_14_days = date.today() + timedelta(days=14)
        task = Task(title="Later task", due=in_14_days)

        sections = reporter._categorize_tasks([task])

        assert len(sections) == 1
        assert sections[0].heading == "Due Later"
        assert sections[0].count == 1

    def test_categorize_no_due_date(self, reporter):
        """Test tasks without due dates go to No Due Date."""
        task = Task(title="No date task")

        sections = reporter._categorize_tasks([task])

        assert len(sections) == 1
        assert sections[0].heading == "No Due Date"
        assert sections[0].count == 1

    def test_categorize_multiple_sections(self, reporter):
        """Test tasks spread across multiple categories."""
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        in_3_days = date.today() + timedelta(days=3)

        tasks = [
            Task(title="Overdue", due=yesterday),
            Task(title="Today", due=today),
            Task(title="This week", due=in_3_days),
            Task(title="No date"),
        ]

        sections = reporter._categorize_tasks(tasks)

        headings = [s.heading for s in sections]
        assert headings == ["Overdue", "Due Today", "Due This Week", "No Due Date"]
        assert all(s.count == 1 for s in sections)

    def test_categorize_empty(self, reporter):
        """Test categorizing empty task list."""
        sections = reporter._categorize_tasks([])

        assert sections == []

    def test_categorize_omits_empty_sections(self, reporter):
        """Test that sections with no tasks are not included."""
        today = date.today()
        tasks = [Task(title="Today", due=today)]

        sections = reporter._categorize_tasks(tasks)

        assert len(sections) == 1
        assert sections[0].heading == "Due Today"


# ==================== Build Report Tests ====================


class TestBuildReport:
    """Tests for building digest reports."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock TaskManager."""
        tm = MagicMock()
        tm.get_or_create_default_list.return_value = MagicMock(
            id="default_list", title="Email Tasks"
        )
        return tm

    @pytest.fixture
    def reporter(self, mock_task_manager):
        """Create a DigestReporter with mocked TaskManager."""
        return DigestReporter(task_manager=mock_task_manager)

    def test_build_report_empty(self, reporter, mock_task_manager):
        """Test building report with no pending tasks."""
        mock_task_manager.list_tasks.return_value = iter([])

        report = reporter.build_report()

        assert report.is_empty is True
        assert report.total_pending == 0
        assert report.total_overdue == 0
        assert report.sections == []
        assert report.task_list_name == "Email Tasks"

    def test_build_report_with_tasks(self, reporter, mock_task_manager):
        """Test building report with pending tasks."""
        today = date.today()
        tasks = [
            Task(title="Task 1", due=today),
            Task(title="Task 2"),
        ]
        mock_task_manager.list_tasks.return_value = iter(tasks)

        report = reporter.build_report()

        assert report.total_pending == 2
        assert report.is_empty is False
        assert len(report.sections) == 2

    def test_build_report_counts_overdue(self, reporter, mock_task_manager):
        """Test that overdue tasks are counted correctly."""
        yesterday = date.today() - timedelta(days=1)
        tasks = [
            Task(title="Overdue 1", due=yesterday),
            Task(title="Overdue 2", due=yesterday - timedelta(days=1)),
            Task(title="Not overdue"),
        ]
        mock_task_manager.list_tasks.return_value = iter(tasks)

        report = reporter.build_report()

        assert report.total_overdue == 2
        assert report.total_pending == 3

    def test_build_report_uses_default_list(self, reporter, mock_task_manager):
        """Test that build_report fetches from default list."""
        mock_task_manager.list_tasks.return_value = iter([])

        reporter.build_report()

        mock_task_manager.list_tasks.assert_called_once_with(
            list_id="default_list", show_completed=False
        )

    def test_build_report_with_custom_list_id(self, reporter, mock_task_manager):
        """Test building report for a specific task list."""
        mock_task_manager.list_tasks.return_value = iter([])

        reporter.build_report(list_id="custom_list")

        mock_task_manager.list_tasks.assert_called_once_with(
            list_id="custom_list", show_completed=False
        )

    def test_build_report_api_error(self, reporter, mock_task_manager):
        """Test that API errors are wrapped in DigestBuildError."""
        mock_task_manager.list_tasks.side_effect = Exception("API unavailable")

        with pytest.raises(DigestBuildError) as exc_info:
            reporter.build_report()

        assert "API unavailable" in exc_info.value.reason


# ==================== Format Plain Text Tests ====================


class TestFormatPlainText:
    """Tests for plain text formatting."""

    @pytest.fixture
    def reporter(self):
        """Create a DigestReporter instance."""
        return DigestReporter()

    def test_format_empty_report(self, reporter):
        """Test formatting an empty digest."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            total_pending=0,
            task_list_name="Email Tasks",
        )

        text = reporter.format_plain_text(report)

        assert "No pending tasks" in text
        assert "all caught up" in text

    def test_format_with_tasks(self, reporter):
        """Test formatting a report with tasks."""
        yesterday = date.today() - timedelta(days=1)
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(
                    heading="Overdue",
                    tasks=[Task(title="Reply to budget proposal", due=yesterday)],
                ),
                DigestSection(
                    heading="No Due Date",
                    tasks=[Task(title="Update docs")],
                ),
            ],
            total_pending=2,
            total_overdue=1,
            task_list_name="Email Tasks",
        )

        text = reporter.format_plain_text(report)

        assert "2 pending tasks (1 overdue)" in text
        assert "--- Overdue (1) ---" in text
        assert "Reply to budget proposal" in text
        assert "--- No Due Date (1) ---" in text
        assert "Update docs" in text

    def test_format_task_with_due_date(self, reporter):
        """Test that due dates are shown in task lines."""
        due = date(2026, 2, 15)
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(heading="Due This Week", tasks=[Task(title="Test", due=due)]),
            ],
            total_pending=1,
        )

        text = reporter.format_plain_text(report)

        assert "(due: 2026-02-15)" in text

    def test_format_task_without_due_date(self, reporter):
        """Test tasks without due dates don't show date."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(heading="No Due Date", tasks=[Task(title="No date task")]),
            ],
            total_pending=1,
        )

        text = reporter.format_plain_text(report)

        assert "- [ ] No date task" in text
        assert "(due:" not in text.split("No date task")[1].split("\n")[0]

    def test_format_header_includes_metadata(self, reporter):
        """Test report header contains date and list name."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            task_list_name="Email Tasks",
            total_pending=0,
        )

        text = reporter.format_plain_text(report)

        assert "Daily Task Digest" in text
        assert "2026-02-10 09:00" in text
        assert "Email Tasks" in text

    def test_format_singular_task_count(self, reporter):
        """Test summary uses singular 'task' for count of 1."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(heading="No Due Date", tasks=[Task(title="Only task")]),
            ],
            total_pending=1,
        )

        text = reporter.format_plain_text(report)

        assert "1 pending task" in text
        assert "1 pending tasks" not in text

    def test_format_no_overdue_omits_overdue_count(self, reporter):
        """Test that overdue count is omitted when zero."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(heading="No Due Date", tasks=[Task(title="Task")]),
            ],
            total_pending=1,
            total_overdue=0,
        )

        text = reporter.format_plain_text(report)

        assert "overdue" not in text.lower()

    def test_format_header_includes_google_tasks_link(self, reporter):
        """Test that header contains link to Google Tasks."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            task_list_name="Email Tasks",
            total_pending=0,
        )

        text = reporter.format_plain_text(report)

        assert "https://tasks.google.com/embed/list/~default" in text

    def test_format_task_with_email_link(self, reporter):
        """Test that tasks with source_thread_id show email link."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(
                    heading="No Due Date",
                    tasks=[Task(title="Reply to Alice", source_thread_id="thread_abc123")],
                ),
            ],
            total_pending=1,
        )

        text = reporter.format_plain_text(report)

        assert "  - Email: https://mail.google.com/mail/#all/thread_abc123" in text

    def test_format_task_without_email_link(self, reporter):
        """Test that tasks without source_thread_id don't show email link."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(
                    heading="No Due Date",
                    tasks=[Task(title="Manual task")],
                ),
            ],
            total_pending=1,
        )

        text = reporter.format_plain_text(report)

        assert "Email:" not in text

    def test_format_task_with_short_description(self, reporter):
        """Test that tasks with short notes show full description."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(
                    heading="No Due Date",
                    tasks=[Task(title="Review PR", notes="Check the new auth module")],
                ),
            ],
            total_pending=1,
        )

        text = reporter.format_plain_text(report)

        assert "  - Check the new auth module" in text
        assert "..." not in text.split("Check the new auth module")[0]

    def test_format_task_with_long_description_truncated(self, reporter):
        """Test that notes longer than 100 chars are truncated with ellipsis."""
        long_notes = "A" * 150
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(
                    heading="No Due Date",
                    tasks=[Task(title="Big task", notes=long_notes)],
                ),
            ],
            total_pending=1,
        )

        text = reporter.format_plain_text(report)

        assert f"  - {'A' * 100}..." in text
        assert "A" * 101 not in text

    def test_format_task_without_notes_no_description(self, reporter):
        """Test that tasks without notes don't show description sub-bullet."""
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(
                    heading="No Due Date",
                    tasks=[Task(title="No notes task")],
                ),
            ],
            total_pending=1,
        )

        text = reporter.format_plain_text(report)
        task_lines = text.split("- [ ] No notes task")[1].split("\n")

        # The line after the task should be empty (section gap) or separator, not a sub-bullet
        assert not any(line.startswith("  - ") for line in task_lines[:2] if "Email:" not in line and "https://tasks" not in line)

    def test_format_task_with_exactly_100_char_notes(self, reporter):
        """Test that notes of exactly 100 chars are shown without ellipsis."""
        notes_100 = "B" * 100
        report = DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(
                    heading="No Due Date",
                    tasks=[Task(title="Boundary task", notes=notes_100)],
                ),
            ],
            total_pending=1,
        )

        text = reporter.format_plain_text(report)

        assert f"  - {'B' * 100}" in text
        assert "..." not in text.split("B" * 100)[1].split("\n")[0]


# ==================== Send Email Tests ====================


class TestSendEmail:
    """Tests for sending digest via email."""

    @pytest.fixture
    def mock_gmail_service(self):
        """Create a mock Gmail API service."""
        return MagicMock()

    @pytest.fixture
    def reporter(self, mock_gmail_service):
        """Create a DigestReporter with mocked Gmail service."""
        return DigestReporter(gmail_service=mock_gmail_service)

    @pytest.fixture
    def sample_report(self):
        """Create a sample digest report."""
        return DigestReport(
            generated_at=datetime(2026, 2, 10, 9, 0, 0),
            sections=[
                DigestSection(heading="No Due Date", tasks=[Task(title="Test task")]),
            ],
            total_pending=1,
            task_list_name="Email Tasks",
        )

    def test_send_email_success(self, reporter, mock_gmail_service, sample_report):
        """Test successfully sending a digest email."""
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "sent_msg_123"
        }

        message_id = reporter.send_email(sample_report, "user@example.com")

        assert message_id == "sent_msg_123"

    def test_send_email_calls_gmail_api(self, reporter, mock_gmail_service, sample_report):
        """Test that Gmail API send endpoint is called."""
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "msg1"
        }

        reporter.send_email(sample_report, "user@example.com")

        mock_gmail_service.users().messages().send.assert_called()

    def test_send_email_correct_subject(self, reporter, mock_gmail_service, sample_report):
        """Test that email subject contains the date."""
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "msg1"
        }

        reporter.send_email(sample_report, "user@example.com")

        call_args = mock_gmail_service.users().messages().send.call_args
        raw_body = call_args.kwargs.get("body", {}).get("raw", "")

        # Decode the base64 message to check subject
        import base64

        decoded = base64.urlsafe_b64decode(raw_body).decode()
        assert "Daily Task Digest - 2026-02-10" in decoded

    def test_send_email_api_error(self, reporter, mock_gmail_service, sample_report):
        """Test that HttpError is wrapped in DigestDeliveryError."""
        resp = MagicMock()
        resp.status = 403
        mock_gmail_service.users().messages().send().execute.side_effect = HttpError(
            resp=resp, content=b"Forbidden"
        )

        with pytest.raises(DigestDeliveryError) as exc_info:
            reporter.send_email(sample_report, "user@example.com")

        assert exc_info.value.reason is not None

    def test_send_email_body_matches_plain_text(
        self, reporter, mock_gmail_service, sample_report
    ):
        """Test that email body matches format_plain_text output."""
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "msg1"
        }

        expected_body = reporter.format_plain_text(sample_report)
        reporter.send_email(sample_report, "user@example.com")

        call_args = mock_gmail_service.users().messages().send.call_args
        raw_body = call_args.kwargs.get("body", {}).get("raw", "")

        import base64

        decoded = base64.urlsafe_b64decode(raw_body).decode()
        # The plain text body should be present in the MIME message
        assert expected_body in decoded


# ==================== Generate and Send Tests ====================


class TestGenerateAndSend:
    """Tests for the main generate_and_send method."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock TaskManager."""
        tm = MagicMock()
        tm.get_or_create_default_list.return_value = MagicMock(
            id="default_list", title="Email Tasks"
        )
        return tm

    @pytest.fixture
    def mock_gmail_service(self):
        """Create a mock Gmail API service."""
        return MagicMock()

    @pytest.fixture
    def reporter(self, mock_task_manager, mock_gmail_service):
        """Create a DigestReporter with all dependencies mocked."""
        return DigestReporter(
            task_manager=mock_task_manager,
            gmail_service=mock_gmail_service,
        )

    def test_generate_plain_text_only(self, reporter, mock_task_manager):
        """Test generating digest without sending email."""
        mock_task_manager.list_tasks.return_value = iter([Task(title="Test")])

        result = reporter.generate_and_send()

        assert result.plain_text_output != ""
        assert result.email_sent is False
        assert result.email_recipient == ""
        assert result.has_errors is False

    def test_generate_and_send_email(
        self, reporter, mock_task_manager, mock_gmail_service
    ):
        """Test generating digest and sending email."""
        mock_task_manager.list_tasks.return_value = iter([Task(title="Test")])
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "sent_123"
        }

        result = reporter.generate_and_send(recipient="user@example.com")

        assert result.plain_text_output != ""
        assert result.email_sent is True
        assert result.email_recipient == "user@example.com"
        assert result.email_message_id == "sent_123"
        assert result.has_errors is False

    def test_generate_handles_build_error(self, reporter, mock_task_manager):
        """Test that build errors are recorded in result."""
        mock_task_manager.list_tasks.side_effect = Exception("API down")

        result = reporter.generate_and_send()

        assert result.has_errors is True
        assert any("Build failed" in e for e in result.errors)
        assert result.plain_text_output == ""

    def test_generate_handles_send_error(
        self, reporter, mock_task_manager, mock_gmail_service
    ):
        """Test that send errors are recorded but plain text is still returned."""
        mock_task_manager.list_tasks.return_value = iter([Task(title="Test")])
        resp = MagicMock()
        resp.status = 500
        mock_gmail_service.users().messages().send().execute.side_effect = HttpError(
            resp=resp, content=b"Server error"
        )

        result = reporter.generate_and_send(recipient="user@example.com")

        assert result.plain_text_output != ""
        assert result.email_sent is False
        assert result.has_errors is True
        assert any("Email delivery failed" in e for e in result.errors)

    def test_generate_empty_digest(self, reporter, mock_task_manager):
        """Test generating an empty digest."""
        mock_task_manager.list_tasks.return_value = iter([])

        result = reporter.generate_and_send()

        assert result.plain_text_output != ""
        assert "No pending tasks" in result.plain_text_output
        assert result.has_errors is False

    def test_generate_result_always_has_plain_text(
        self, reporter, mock_task_manager, mock_gmail_service
    ):
        """Test that result always contains plain text output on success."""
        mock_task_manager.list_tasks.return_value = iter(
            [Task(title="Task 1"), Task(title="Task 2")]
        )
        mock_gmail_service.users().messages().send().execute.return_value = {
            "id": "msg1"
        }

        result = reporter.generate_and_send(recipient="user@example.com")

        assert "Task 1" in result.plain_text_output
        assert "Task 2" in result.plain_text_output
