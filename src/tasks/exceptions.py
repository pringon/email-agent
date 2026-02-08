"""Exceptions for the tasks module."""


class TasksError(Exception):
    """Base exception for all tasks-related errors."""

    pass


class TasksAuthError(TasksError):
    """Raised when Google Tasks authentication fails."""

    pass


class TasksAPIError(TasksError):
    """Raised when a Google Tasks API call fails."""

    def __init__(self, message: str, status_code: int | None = None, reason: str | None = None):
        self.status_code = status_code
        self.reason = reason
        super().__init__(message)


class TaskNotFoundError(TasksError):
    """Raised when a requested task does not exist."""

    def __init__(self, task_id: str, task_list_id: str | None = None):
        self.task_id = task_id
        self.task_list_id = task_list_id
        location = f" in list '{task_list_id}'" if task_list_id else ""
        super().__init__(f"Task '{task_id}' not found{location}")


class TaskListNotFoundError(TasksError):
    """Raised when a requested task list does not exist."""

    def __init__(self, task_list_id: str):
        self.task_list_id = task_list_id
        super().__init__(f"Task list '{task_list_id}' not found")


class RateLimitError(TasksError):
    """Raised when API rate limits are exceeded."""

    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        msg = "Google Tasks API rate limit exceeded"
        if retry_after:
            msg += f". Retry after {retry_after} seconds"
        super().__init__(msg)
