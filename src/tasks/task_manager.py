"""TaskManager for Google Tasks API integration."""

import logging
from typing import Iterator, Optional

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from src.analyzer.models import ExtractedTask, Priority

from .exceptions import (
    RateLimitError,
    TaskListNotFoundError,
    TaskNotFoundError,
    TasksAPIError,
)
from .models import Task, TaskList, TaskStatus
from .tasks_auth import TasksAuthenticator

logger = logging.getLogger(__name__)

# Default task list name for email-generated tasks
DEFAULT_LIST_NAME = "Email Tasks"


class TaskManager:
    """Manages tasks in Google Tasks.

    Provides CRUD operations for tasks and task lists, with special
    support for tasks created from email analysis.
    """

    def __init__(
        self,
        authenticator: Optional[TasksAuthenticator] = None,
        default_list_name: str = DEFAULT_LIST_NAME,
    ):
        """Initialize the TaskManager.

        Args:
            authenticator: TasksAuthenticator instance for API access.
                Created automatically if not provided.
            default_list_name: Name of the task list to use for email tasks.
                Created if it doesn't exist.
        """
        self._authenticator = authenticator or TasksAuthenticator()
        self._service: Optional[Resource] = None
        self._default_list_name = default_list_name
        self._default_list_id: Optional[str] = None

    def _get_service(self) -> Resource:
        """Get the Google Tasks API service."""
        if self._service is None:
            self._service = self._authenticator.get_service()
        return self._service

    def _handle_http_error(self, error: HttpError, context: str = "") -> None:
        """Convert HttpError to appropriate exception.

        Args:
            error: The HttpError from the API call.
            context: Additional context for error message.

        Raises:
            TaskNotFoundError: If the error indicates a 404.
            RateLimitError: If the error indicates rate limiting (429).
            TasksAPIError: For other API errors.
        """
        status_code = error.resp.status
        reason = error.reason if hasattr(error, "reason") else str(error)
        logger.error("Google Tasks API error (status=%d): %s", status_code, reason)

        if status_code == 404:
            raise TaskNotFoundError(task_id=context) from error
        elif status_code == 429:
            retry_after = error.resp.get("retry-after")
            raise RateLimitError(
                retry_after=int(retry_after) if retry_after else None
            ) from error
        else:
            msg = f"Google Tasks API error: {reason}"
            if context:
                msg = f"{context}: {msg}"
            raise TasksAPIError(msg, status_code=status_code, reason=reason) from error

    # -------------------- Task List Operations --------------------

    def list_task_lists(self) -> list[TaskList]:
        """Get all task lists for the user.

        Returns:
            List of TaskList objects.

        Raises:
            TasksAPIError: If the API call fails.
        """
        try:
            service = self._get_service()
            result = service.tasklists().list().execute()
            items = result.get("items", [])
            return [TaskList.from_api_response(item) for item in items]
        except HttpError as e:
            self._handle_http_error(e, "Failed to list task lists")
            raise  # Never reached, but satisfies type checker

    def get_task_list(self, list_id: str) -> TaskList:
        """Get a specific task list by ID.

        Args:
            list_id: The task list ID.

        Returns:
            TaskList object.

        Raises:
            TaskListNotFoundError: If the list doesn't exist.
            TasksAPIError: If the API call fails.
        """
        try:
            service = self._get_service()
            result = service.tasklists().get(tasklist=list_id).execute()
            return TaskList.from_api_response(result)
        except HttpError as e:
            if e.resp.status == 404:
                raise TaskListNotFoundError(list_id) from e
            self._handle_http_error(e, f"Failed to get task list {list_id}")
            raise

    def create_task_list(self, title: str) -> TaskList:
        """Create a new task list.

        Args:
            title: Title for the new task list.

        Returns:
            Created TaskList object.

        Raises:
            TasksAPIError: If the API call fails.
        """
        try:
            service = self._get_service()
            result = service.tasklists().insert(body={"title": title}).execute()
            return TaskList.from_api_response(result)
        except HttpError as e:
            self._handle_http_error(e, f"Failed to create task list '{title}'")
            raise

    def get_or_create_default_list(self) -> TaskList:
        """Get the default task list for email tasks, creating if needed.

        Returns:
            TaskList for storing email-generated tasks.
        """
        # Check cache first
        if self._default_list_id:
            try:
                return self.get_task_list(self._default_list_id)
            except TaskListNotFoundError:
                self._default_list_id = None

        # Search for existing list
        for task_list in self.list_task_lists():
            if task_list.title == self._default_list_name:
                self._default_list_id = task_list.id
                logger.debug("Using existing task list '%s' (id=%s)", task_list.title, task_list.id)
                return task_list

        # Create new list
        task_list = self.create_task_list(self._default_list_name)
        self._default_list_id = task_list.id
        logger.info("Created task list '%s' (id=%s)", task_list.title, task_list.id)
        return task_list

    # -------------------- Task CRUD Operations --------------------

    def create_task(self, task: Task, list_id: Optional[str] = None) -> Task:
        """Create a new task.

        Args:
            task: Task object to create (id field is ignored).
            list_id: Task list to create in. Uses default list if not specified.

        Returns:
            Created Task with ID populated.

        Raises:
            TaskListNotFoundError: If the specified list doesn't exist.
            TasksAPIError: If the API call fails.
        """
        if list_id is None:
            default_list = self.get_or_create_default_list()
            list_id = default_list.id

        try:
            service = self._get_service()
            body = task.to_api_body()
            result = service.tasks().insert(tasklist=list_id, body=body).execute()
            created = Task.from_api_response(result, task_list_id=list_id)
            logger.info("Created task '%s' (id=%s)", created.title, created.id)
            return created
        except HttpError as e:
            if e.resp.status == 404:
                raise TaskListNotFoundError(list_id) from e
            self._handle_http_error(e, "Failed to create task")
            raise

    def get_task(self, task_id: str, list_id: Optional[str] = None) -> Task:
        """Get a specific task by ID.

        Args:
            task_id: The task ID.
            list_id: Task list ID. Uses default list if not specified.

        Returns:
            Task object.

        Raises:
            TaskNotFoundError: If the task doesn't exist.
            TasksAPIError: If the API call fails.
        """
        if list_id is None:
            default_list = self.get_or_create_default_list()
            list_id = default_list.id

        try:
            service = self._get_service()
            result = service.tasks().get(tasklist=list_id, task=task_id).execute()
            return Task.from_api_response(result, task_list_id=list_id)
        except HttpError as e:
            if e.resp.status == 404:
                raise TaskNotFoundError(task_id, list_id) from e
            self._handle_http_error(e, f"Failed to get task {task_id}")
            raise

    def update_task(self, task: Task, list_id: Optional[str] = None) -> Task:
        """Update an existing task.

        Args:
            task: Task object with updates. Must have id set.
            list_id: Task list ID. Uses task's list_id or default if not specified.

        Returns:
            Updated Task object.

        Raises:
            ValueError: If task has no ID.
            TaskNotFoundError: If the task doesn't exist.
            TasksAPIError: If the API call fails.
        """
        if not task.id:
            raise ValueError("Cannot update task without an ID")

        if list_id is None:
            list_id = task.task_list_id
        if list_id is None:
            default_list = self.get_or_create_default_list()
            list_id = default_list.id

        try:
            service = self._get_service()
            body = task.to_api_body()
            result = (
                service.tasks()
                .update(tasklist=list_id, task=task.id, body=body)
                .execute()
            )
            return Task.from_api_response(result, task_list_id=list_id)
        except HttpError as e:
            if e.resp.status == 404:
                raise TaskNotFoundError(task.id, list_id) from e
            self._handle_http_error(e, f"Failed to update task {task.id}")
            raise

    def delete_task(self, task_id: str, list_id: Optional[str] = None) -> None:
        """Delete a task.

        Args:
            task_id: The task ID to delete.
            list_id: Task list ID. Uses default list if not specified.

        Raises:
            TaskNotFoundError: If the task doesn't exist.
            TasksAPIError: If the API call fails.
        """
        if list_id is None:
            default_list = self.get_or_create_default_list()
            list_id = default_list.id

        try:
            service = self._get_service()
            service.tasks().delete(tasklist=list_id, task=task_id).execute()
        except HttpError as e:
            if e.resp.status == 404:
                raise TaskNotFoundError(task_id, list_id) from e
            self._handle_http_error(e, f"Failed to delete task {task_id}")
            raise

    def list_tasks(
        self,
        list_id: Optional[str] = None,
        show_completed: bool = False,
        show_hidden: bool = False,
        max_results: int = 100,
    ) -> Iterator[Task]:
        """List tasks in a task list.

        Args:
            list_id: Task list ID. Uses default list if not specified.
            show_completed: Include completed tasks.
            show_hidden: Include hidden tasks.
            max_results: Maximum number of tasks per page.

        Yields:
            Task objects.

        Raises:
            TaskListNotFoundError: If the specified list doesn't exist.
            TasksAPIError: If the API call fails.
        """
        if list_id is None:
            default_list = self.get_or_create_default_list()
            list_id = default_list.id

        try:
            service = self._get_service()
            page_token = None

            while True:
                result = (
                    service.tasks()
                    .list(
                        tasklist=list_id,
                        showCompleted=show_completed,
                        showHidden=show_hidden,
                        maxResults=max_results,
                        pageToken=page_token,
                    )
                    .execute()
                )

                for item in result.get("items", []):
                    yield Task.from_api_response(item, task_list_id=list_id)

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

        except HttpError as e:
            if e.resp.status == 404:
                raise TaskListNotFoundError(list_id) from e
            self._handle_http_error(e, f"Failed to list tasks in {list_id}")
            raise

    # -------------------- Task Status Operations --------------------

    def complete_task(self, task_id: str, list_id: Optional[str] = None) -> Task:
        """Mark a task as completed.

        Args:
            task_id: The task ID to complete.
            list_id: Task list ID. Uses default list if not specified.

        Returns:
            Updated Task object.

        Raises:
            TaskNotFoundError: If the task doesn't exist.
            TasksAPIError: If the API call fails.
        """
        task = self.get_task(task_id, list_id)
        task.mark_completed()
        updated = self.update_task(task, list_id)
        logger.info("Marked task %s as completed", task_id)
        return updated

    def uncomplete_task(self, task_id: str, list_id: Optional[str] = None) -> Task:
        """Mark a task as needing action.

        Args:
            task_id: The task ID to uncomplete.
            list_id: Task list ID. Uses default list if not specified.

        Returns:
            Updated Task object.

        Raises:
            TaskNotFoundError: If the task doesn't exist.
            TasksAPIError: If the API call fails.
        """
        task = self.get_task(task_id, list_id)
        task.mark_incomplete()
        return self.update_task(task, list_id)

    # -------------------- Email Integration --------------------

    def create_from_extracted_task(
        self,
        extracted: ExtractedTask,
        list_id: Optional[str] = None,
    ) -> Task:
        """Create a Google Task from an ExtractedTask.

        Converts the analyzer's ExtractedTask into a Google Task with
        appropriate metadata for tracking the source email.

        Args:
            extracted: ExtractedTask from email analysis.
            list_id: Task list ID. Uses default list if not specified.

        Returns:
            Created Task with ID populated.
        """
        # Build notes with priority and context
        notes_parts = []
        notes_parts.append(f"Priority: {extracted.priority.value}")
        if extracted.confidence < 1.0:
            notes_parts.append(f"Confidence: {extracted.confidence:.0%}")
        if extracted.source_thread_id:
            notes_parts.append(
                f"Email: https://mail.google.com/mail/#all/{extracted.source_thread_id}"
            )
        notes_parts.append("")
        notes_parts.append(extracted.description)

        task = Task(
            title=extracted.title,
            notes="\n".join(notes_parts),
            due=extracted.due_date,
            source_email_id=extracted.source_email_id,
            source_thread_id=extracted.source_thread_id,
        )

        return self.create_task(task, list_id)

    def find_tasks_by_thread_id(
        self,
        thread_id: str,
        list_id: Optional[str] = None,
        include_completed: bool = True,
    ) -> list[Task]:
        """Find all tasks associated with an email thread.

        Used for T07 (linking tasks to email threads) and T08 (completion detection).

        Args:
            thread_id: Gmail thread ID to search for.
            list_id: Task list ID. Uses default list if not specified.
            include_completed: Whether to include completed tasks.

        Returns:
            List of tasks associated with the thread.
        """
        matching_tasks = []
        for task in self.list_tasks(list_id, show_completed=include_completed):
            if task.source_thread_id == thread_id:
                matching_tasks.append(task)
        logger.debug("Thread %s: found %d matching tasks", thread_id, len(matching_tasks))
        return matching_tasks

    def find_tasks_by_email_id(
        self,
        email_id: str,
        list_id: Optional[str] = None,
        include_completed: bool = True,
    ) -> list[Task]:
        """Find all tasks associated with a specific email message.

        Args:
            email_id: Gmail message ID to search for.
            list_id: Task list ID. Uses default list if not specified.
            include_completed: Whether to include completed tasks.

        Returns:
            List of tasks associated with the email.
        """
        matching_tasks = []
        for task in self.list_tasks(list_id, show_completed=include_completed):
            if task.source_email_id == email_id:
                matching_tasks.append(task)
        return matching_tasks

    def complete_tasks_for_thread(
        self,
        thread_id: str,
        list_id: Optional[str] = None,
    ) -> list[Task]:
        """Mark all tasks for an email thread as completed.

        Used when a reply is detected to the originating email thread.

        Args:
            thread_id: Gmail thread ID.
            list_id: Task list ID. Uses default list if not specified.

        Returns:
            List of tasks that were marked as completed.
        """
        completed_tasks = []
        for task in self.find_tasks_by_thread_id(
            thread_id, list_id, include_completed=False
        ):
            completed_task = self.complete_task(task.id, list_id)
            completed_tasks.append(completed_task)
        logger.info("Completed %d tasks for thread %s", len(completed_tasks), thread_id)
        return completed_tasks
