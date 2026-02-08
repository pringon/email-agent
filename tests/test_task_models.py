"""Unit tests for Task models, exceptions, and authenticator."""

from datetime import date, datetime

import pytest

from src.tasks import (
    RateLimitError,
    Task,
    TaskList,
    TaskListNotFoundError,
    TaskNotFoundError,
    TasksAPIError,
    TaskStatus,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_needs_action_value(self):
        """Test NEEDS_ACTION has correct API value."""
        assert TaskStatus.NEEDS_ACTION.value == "needsAction"

    def test_completed_value(self):
        """Test COMPLETED has correct API value."""
        assert TaskStatus.COMPLETED.value == "completed"


class TestTaskList:
    """Tests for TaskList dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        task_list = TaskList(
            id="list123",
            title="My Tasks",
            updated=datetime(2024, 1, 15, 10, 30, 0),
        )
        data = task_list.to_dict()
        assert data["id"] == "list123"
        assert data["title"] == "My Tasks"
        assert data["updated"] == "2024-01-15T10:30:00"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "list123",
            "title": "My Tasks",
            "updated": "2024-01-15T10:30:00+00:00",
        }
        task_list = TaskList.from_dict(data)
        assert task_list.id == "list123"
        assert task_list.title == "My Tasks"
        assert task_list.updated is not None

    def test_from_api_response(self):
        """Test creation from API response."""
        data = {
            "id": "list123",
            "title": "My Tasks",
            "updated": "2024-01-15T10:30:00.000Z",
        }
        task_list = TaskList.from_api_response(data)
        assert task_list.id == "list123"
        assert task_list.title == "My Tasks"


class TestTask:
    """Tests for Task dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        task = Task(
            id="task123",
            title="Test Task",
            notes="Some notes",
            status=TaskStatus.NEEDS_ACTION,
            due=date(2024, 1, 20),
            source_email_id="email123",
            source_thread_id="thread456",
        )
        data = task.to_dict()
        assert data["id"] == "task123"
        assert data["title"] == "Test Task"
        assert data["notes"] == "Some notes"
        assert data["status"] == "needsAction"
        assert data["due"] == "2024-01-20"
        assert data["source_email_id"] == "email123"
        assert data["source_thread_id"] == "thread456"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "task123",
            "title": "Test Task",
            "notes": "Some notes",
            "status": "needsAction",
            "due": "2024-01-20",
            "source_email_id": "email123",
            "source_thread_id": "thread456",
        }
        task = Task.from_dict(data)
        assert task.id == "task123"
        assert task.title == "Test Task"
        assert task.due == date(2024, 1, 20)

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = Task(
            id="task123",
            title="Test Task",
            notes="Some notes",
            status=TaskStatus.COMPLETED,
            due=date(2024, 1, 20),
            completed=datetime(2024, 1, 18, 14, 30),
            source_email_id="email123",
            source_thread_id="thread456",
        )
        restored = Task.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.status == original.status
        assert restored.due == original.due

    def test_to_api_body_minimal(self):
        """Test API body generation with minimal fields."""
        task = Task(title="Test Task")
        body = task.to_api_body()
        assert body["title"] == "Test Task"
        assert body["status"] == "needsAction"
        assert "notes" not in body
        assert "due" not in body

    def test_to_api_body_with_metadata(self):
        """Test API body includes email metadata in notes."""
        task = Task(
            title="Test Task",
            notes="Original notes",
            source_email_id="email123",
            source_thread_id="thread456",
        )
        body = task.to_api_body()
        assert "Original notes" in body["notes"]
        assert "email_id:email123" in body["notes"]
        assert "thread_id:thread456" in body["notes"]
        assert Task.METADATA_PREFIX in body["notes"]

    def test_to_api_body_with_due_date(self):
        """Test API body formats due date correctly."""
        task = Task(title="Test Task", due=date(2024, 1, 20))
        body = task.to_api_body()
        assert body["due"] == "2024-01-20T00:00:00.000Z"

    def test_to_api_body_truncates_title(self):
        """Test API body truncates long titles to 1024 chars."""
        task = Task(title="x" * 2000)
        body = task.to_api_body()
        assert len(body["title"]) == 1024

    def test_from_api_response_basic(self):
        """Test creation from API response."""
        data = {
            "id": "task123",
            "title": "Test Task",
            "status": "needsAction",
        }
        task = Task.from_api_response(data, task_list_id="list123")
        assert task.id == "task123"
        assert task.title == "Test Task"
        assert task.task_list_id == "list123"

    def test_from_api_response_extracts_metadata(self):
        """Test metadata extraction from notes."""
        data = {
            "id": "task123",
            "title": "Test Task",
            "notes": f"Some notes\n\n{Task.METADATA_PREFIX}\nemail_id:email123\nthread_id:thread456",
            "status": "needsAction",
        }
        task = Task.from_api_response(data)
        assert task.notes == "Some notes"
        assert task.source_email_id == "email123"
        assert task.source_thread_id == "thread456"

    def test_from_api_response_with_due_date(self):
        """Test due date parsing from API response."""
        data = {
            "id": "task123",
            "title": "Test Task",
            "due": "2024-01-20T00:00:00.000Z",
            "status": "needsAction",
        }
        task = Task.from_api_response(data)
        assert task.due == date(2024, 1, 20)

    def test_from_api_response_with_completed(self):
        """Test completed datetime parsing."""
        data = {
            "id": "task123",
            "title": "Test Task",
            "status": "completed",
            "completed": "2024-01-18T14:30:00.000Z",
        }
        task = Task.from_api_response(data)
        assert task.status == TaskStatus.COMPLETED
        assert task.completed is not None

    def test_is_completed_property(self):
        """Test is_completed property."""
        task = Task(title="Test", status=TaskStatus.NEEDS_ACTION)
        assert not task.is_completed

        task.status = TaskStatus.COMPLETED
        assert task.is_completed

    def test_mark_completed(self):
        """Test marking task as completed."""
        task = Task(title="Test")
        task.mark_completed()
        assert task.status == TaskStatus.COMPLETED
        assert task.completed is not None

    def test_mark_incomplete(self):
        """Test marking task as incomplete."""
        task = Task(title="Test", status=TaskStatus.COMPLETED, completed=datetime.now())
        task.mark_incomplete()
        assert task.status == TaskStatus.NEEDS_ACTION
        assert task.completed is None


class TestExceptions:
    """Tests for exception classes."""

    def test_task_not_found_message(self):
        """Test TaskNotFoundError message formatting."""
        error = TaskNotFoundError("task123", "list456")
        assert "task123" in str(error)
        assert "list456" in str(error)

    def test_task_not_found_without_list(self):
        """Test TaskNotFoundError without list ID."""
        error = TaskNotFoundError("task123")
        assert "task123" in str(error)
        assert "list" not in str(error).lower()

    def test_task_list_not_found_message(self):
        """Test TaskListNotFoundError message formatting."""
        error = TaskListNotFoundError("list123")
        assert "list123" in str(error)

    def test_rate_limit_error_with_retry(self):
        """Test RateLimitError with retry-after."""
        error = RateLimitError(retry_after=60)
        assert error.retry_after == 60
        assert "60" in str(error)

    def test_rate_limit_error_without_retry(self):
        """Test RateLimitError without retry-after."""
        error = RateLimitError()
        assert error.retry_after is None

    def test_api_error_attributes(self):
        """Test TasksAPIError attributes."""
        error = TasksAPIError("Something went wrong", status_code=500, reason="Server error")
        assert error.status_code == 500
        assert error.reason == "Server error"
