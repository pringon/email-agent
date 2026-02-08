"""Google Tasks integration module - foundation layer.

This module provides data models, exceptions, and authentication
for the Google Tasks API integration.
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
from .tasks_auth import TasksAuthenticator

__all__ = [
    # Authentication
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
