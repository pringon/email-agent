"""Completion checker module for detecting task completion via Sent Mail.

This module monitors the user's Sent Mail for replies to email threads
that have associated tasks. When a reply is detected, the corresponding
tasks are automatically marked as complete.

Public API:
    CompletionChecker: Main class for detecting and processing completions.
    CompletionResult: Result object with details of a completion check.
    SentEmail: Model representing a sent email.
    CompletionError: Base exception for module errors.
    SentMailAccessError: Raised when Sent Mail cannot be accessed.
"""

from .completion_checker import CompletionChecker
from .exceptions import CompletionError, SentMailAccessError
from .models import CompletionResult, SentEmail

__all__ = [
    "CompletionChecker",
    "CompletionResult",
    "SentEmail",
    "CompletionError",
    "SentMailAccessError",
]
