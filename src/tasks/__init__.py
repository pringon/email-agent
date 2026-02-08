"""Google Tasks integration module.

This module provides the TaskManager for creating, reading, updating,
and deleting tasks in Google Tasks, with special support for tasks
generated from email analysis.
"""

from .exceptions import (
    RateLimitError,
    TaskListNotFoundError,
    TaskNotFoundError,
    TasksAPIError,
    TasksAuthError,
    TasksError,
)
from .models import Task, TaskList, TaskStatus
from .task_manager import TaskManager
from .tasks_auth import TasksAuthenticator

__all__ = [
    # Main classes
    "TaskManager",
    "TasksAuthenticator",
    # Models
    "Task",
    "TaskList",
    "TaskStatus",
    # Exceptions
    "TasksError",
    "TasksAuthError",
    "TasksAPIError",
    "TaskNotFoundError",
    "TaskListNotFoundError",
    "RateLimitError",
]
