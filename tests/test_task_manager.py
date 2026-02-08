"""Unit tests for the TaskManager class."""

from datetime import date
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from src.analyzer.models import ExtractedTask, Priority
from src.tasks import (
    RateLimitError,
    Task,
    TaskListNotFoundError,
    TaskManager,
    TaskNotFoundError,
    TasksAPIError,
    TaskStatus,
)


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
