"""Unit tests for the TaskManager module."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from src.analyzer.models import ExtractedTask, Priority
from src.tasks import (
    RateLimitError,
    Task,
    TaskList,
    TaskListNotFoundError,
    TaskManager,
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


class TestTaskManagerWithMock:
    """Tests for TaskManager with mocked API service."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock Google Tasks service."""
        return MagicMock()

    @pytest.fixture
    def task_manager(self, mock_service):
        """Create a TaskManager with mock service."""
        return TaskManager(service=mock_service)

    # -------------------- Task List Tests --------------------

    def test_list_task_lists(self, task_manager, mock_service):
        """Test listing task lists."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [
                {"id": "list1", "title": "List 1"},
                {"id": "list2", "title": "List 2"},
            ]
        }

        lists = task_manager.list_task_lists()
        assert len(lists) == 2
        assert lists[0].id == "list1"
        assert lists[1].title == "List 2"

    def test_get_task_list(self, task_manager, mock_service):
        """Test getting a specific task list."""
        mock_service.tasklists().get().execute.return_value = {
            "id": "list123",
            "title": "My List",
        }

        task_list = task_manager.get_task_list("list123")
        assert task_list.id == "list123"
        assert task_list.title == "My List"

    def test_create_task_list(self, task_manager, mock_service):
        """Test creating a task list."""
        mock_service.tasklists().insert().execute.return_value = {
            "id": "new_list",
            "title": "New List",
        }

        task_list = task_manager.create_task_list("New List")
        assert task_list.id == "new_list"
        assert task_list.title == "New List"

    def test_get_or_create_default_list_creates_new(self, task_manager, mock_service):
        """Test creating default list when it doesn't exist."""
        mock_service.tasklists().list().execute.return_value = {"items": []}
        mock_service.tasklists().insert().execute.return_value = {
            "id": "new_list",
            "title": "Email Tasks",
        }

        task_list = task_manager.get_or_create_default_list()
        assert task_list.title == "Email Tasks"
        mock_service.tasklists().insert.assert_called()

    def test_get_or_create_default_list_finds_existing(self, task_manager, mock_service):
        """Test finding existing default list."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [
                {"id": "list1", "title": "Other List"},
                {"id": "list2", "title": "Email Tasks"},
            ]
        }

        task_list = task_manager.get_or_create_default_list()
        assert task_list.id == "list2"
        assert task_list.title == "Email Tasks"

    # -------------------- Task CRUD Tests --------------------

    def test_create_task(self, task_manager, mock_service):
        """Test creating a task."""
        # Setup default list
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().insert().execute.return_value = {
            "id": "task123",
            "title": "New Task",
            "status": "needsAction",
        }

        task = Task(title="New Task")
        created = task_manager.create_task(task)

        assert created.id == "task123"
        assert created.title == "New Task"

    def test_create_task_with_list_id(self, task_manager, mock_service):
        """Test creating a task in a specific list."""
        mock_service.tasks().insert().execute.return_value = {
            "id": "task123",
            "title": "New Task",
            "status": "needsAction",
        }

        task = Task(title="New Task")
        created = task_manager.create_task(task, list_id="custom_list")

        assert created.id == "task123"
        mock_service.tasks().insert.assert_called()

    def test_get_task(self, task_manager, mock_service):
        """Test getting a task by ID."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().get().execute.return_value = {
            "id": "task123",
            "title": "Test Task",
            "status": "needsAction",
        }

        task = task_manager.get_task("task123")
        assert task.id == "task123"
        assert task.title == "Test Task"

    def test_update_task(self, task_manager, mock_service):
        """Test updating a task."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().update().execute.return_value = {
            "id": "task123",
            "title": "Updated Task",
            "status": "needsAction",
        }

        task = Task(id="task123", title="Updated Task")
        updated = task_manager.update_task(task)

        assert updated.title == "Updated Task"

    def test_update_task_without_id_raises(self, task_manager):
        """Test that updating task without ID raises ValueError."""
        task = Task(title="No ID Task")
        with pytest.raises(ValueError, match="Cannot update task without an ID"):
            task_manager.update_task(task)

    def test_delete_task(self, task_manager, mock_service):
        """Test deleting a task."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().delete().execute.return_value = None

        task_manager.delete_task("task123")
        mock_service.tasks().delete.assert_called()

    def test_list_tasks(self, task_manager, mock_service):
        """Test listing tasks."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().list().execute.return_value = {
            "items": [
                {"id": "task1", "title": "Task 1", "status": "needsAction"},
                {"id": "task2", "title": "Task 2", "status": "needsAction"},
            ]
        }

        tasks = list(task_manager.list_tasks())
        assert len(tasks) == 2
        assert tasks[0].id == "task1"
        assert tasks[1].id == "task2"

    def test_list_tasks_with_pagination(self, task_manager, mock_service):
        """Test listing tasks handles pagination."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }

        # Return different pages
        mock_service.tasks().list().execute.side_effect = [
            {
                "items": [{"id": "task1", "title": "Task 1", "status": "needsAction"}],
                "nextPageToken": "page2",
            },
            {
                "items": [{"id": "task2", "title": "Task 2", "status": "needsAction"}],
            },
        ]

        tasks = list(task_manager.list_tasks())
        assert len(tasks) == 2

    # -------------------- Task Status Tests --------------------

    def test_complete_task(self, task_manager, mock_service):
        """Test completing a task."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().get().execute.return_value = {
            "id": "task123",
            "title": "Test Task",
            "status": "needsAction",
        }
        mock_service.tasks().update().execute.return_value = {
            "id": "task123",
            "title": "Test Task",
            "status": "completed",
        }

        completed = task_manager.complete_task("task123")
        assert completed.status == TaskStatus.COMPLETED

    def test_uncomplete_task(self, task_manager, mock_service):
        """Test marking task as incomplete."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().get().execute.return_value = {
            "id": "task123",
            "title": "Test Task",
            "status": "completed",
        }
        mock_service.tasks().update().execute.return_value = {
            "id": "task123",
            "title": "Test Task",
            "status": "needsAction",
        }

        task = task_manager.uncomplete_task("task123")
        assert task.status == TaskStatus.NEEDS_ACTION

    # -------------------- Email Integration Tests --------------------

    def test_create_from_extracted_task(self, task_manager, mock_service):
        """Test creating task from ExtractedTask."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().insert().execute.return_value = {
            "id": "task123",
            "title": "Reply to John",
            "notes": f"Priority: high\n\nNeed to respond about the proposal\n\n{Task.METADATA_PREFIX}\nemail_id:email123\nthread_id:thread456",
            "status": "needsAction",
        }

        extracted = ExtractedTask(
            title="Reply to John",
            description="Need to respond about the proposal",
            priority=Priority.HIGH,
            source_email_id="email123",
            source_thread_id="thread456",
            due_date=date(2024, 1, 20),
            confidence=0.9,
        )

        task = task_manager.create_from_extracted_task(extracted)
        assert task.id == "task123"
        assert task.title == "Reply to John"

    def test_find_tasks_by_thread_id(self, task_manager, mock_service):
        """Test finding tasks by thread ID."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().list().execute.return_value = {
            "items": [
                {
                    "id": "task1",
                    "title": "Task 1",
                    "notes": f"{Task.METADATA_PREFIX}\nthread_id:thread123",
                    "status": "needsAction",
                },
                {
                    "id": "task2",
                    "title": "Task 2",
                    "notes": f"{Task.METADATA_PREFIX}\nthread_id:thread456",
                    "status": "needsAction",
                },
                {
                    "id": "task3",
                    "title": "Task 3",
                    "notes": f"{Task.METADATA_PREFIX}\nthread_id:thread123",
                    "status": "needsAction",
                },
            ]
        }

        tasks = task_manager.find_tasks_by_thread_id("thread123")
        assert len(tasks) == 2
        assert all(t.source_thread_id == "thread123" for t in tasks)

    def test_find_tasks_by_email_id(self, task_manager, mock_service):
        """Test finding tasks by email ID."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasks().list().execute.return_value = {
            "items": [
                {
                    "id": "task1",
                    "title": "Task 1",
                    "notes": f"{Task.METADATA_PREFIX}\nemail_id:email123",
                    "status": "needsAction",
                },
                {
                    "id": "task2",
                    "title": "Task 2",
                    "notes": f"{Task.METADATA_PREFIX}\nemail_id:email456",
                    "status": "needsAction",
                },
            ]
        }

        tasks = task_manager.find_tasks_by_email_id("email123")
        assert len(tasks) == 1
        assert tasks[0].source_email_id == "email123"

    def test_complete_tasks_for_thread(self, task_manager, mock_service):
        """Test completing all tasks for a thread."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_service.tasklists().get().execute.return_value = {
            "id": "default_list",
            "title": "Email Tasks",
        }
        mock_service.tasks().list().execute.return_value = {
            "items": [
                {
                    "id": "task1",
                    "title": "Task 1",
                    "notes": f"{Task.METADATA_PREFIX}\nthread_id:thread123",
                    "status": "needsAction",
                },
                {
                    "id": "task2",
                    "title": "Task 2",
                    "notes": f"{Task.METADATA_PREFIX}\nthread_id:thread123",
                    "status": "needsAction",
                },
            ]
        }
        mock_service.tasks().get().execute.return_value = {
            "id": "task1",
            "title": "Task 1",
            "status": "needsAction",
        }
        mock_service.tasks().update().execute.return_value = {
            "id": "task1",
            "title": "Task 1",
            "status": "completed",
        }

        completed = task_manager.complete_tasks_for_thread("thread123")
        # At least one task should be processed (mock returns same for all gets)
        assert len(completed) >= 1

    # -------------------- Error Handling Tests --------------------

    def test_task_not_found_error(self, task_manager, mock_service):
        """Test TaskNotFoundError is raised for 404."""
        mock_service.tasklists().list().execute.return_value = {
            "items": [{"id": "default_list", "title": "Email Tasks"}]
        }
        mock_resp = MagicMock()
        mock_resp.status = 404
        error = HttpError(mock_resp, b"Not found")
        mock_service.tasks().get().execute.side_effect = error

        with pytest.raises(TaskNotFoundError) as exc_info:
            task_manager.get_task("nonexistent")
        assert exc_info.value.task_id == "nonexistent"

    def test_task_list_not_found_error(self, task_manager, mock_service):
        """Test TaskListNotFoundError is raised for 404 on list."""
        mock_resp = MagicMock()
        mock_resp.status = 404
        error = HttpError(mock_resp, b"Not found")
        mock_service.tasklists().get().execute.side_effect = error

        with pytest.raises(TaskListNotFoundError) as exc_info:
            task_manager.get_task_list("nonexistent")
        assert exc_info.value.task_list_id == "nonexistent"

    def test_rate_limit_error(self, task_manager, mock_service):
        """Test RateLimitError is raised for 429."""
        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.get.return_value = "60"
        error = HttpError(mock_resp, b"Rate limit exceeded")
        mock_service.tasklists().list().execute.side_effect = error

        with pytest.raises(RateLimitError) as exc_info:
            task_manager.list_task_lists()
        assert exc_info.value.retry_after == 60

    def test_generic_api_error(self, task_manager, mock_service):
        """Test TasksAPIError for other HTTP errors."""
        mock_resp = MagicMock()
        mock_resp.status = 500
        error = HttpError(mock_resp, b"Internal server error")
        error.reason = "Internal server error"
        mock_service.tasklists().list().execute.side_effect = error

        with pytest.raises(TasksAPIError) as exc_info:
            task_manager.list_task_lists()
        assert exc_info.value.status_code == 500


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
