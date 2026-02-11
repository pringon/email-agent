"""Completion checker module for detecting task completion via Sent Mail.

This module monitors the user's Sent Mail for replies to email threads
that have associated tasks. When a reply is detected, it uses an LLM
(via ReplyResolver) to determine which specific tasks the reply addresses
and marks only those tasks as complete.

Public API:
    CompletionChecker: Main class for detecting and processing completions.
    ReplyResolver: LLM-based resolver for matching replies to tasks.
    CompletionResult: Result object with details of a completion check.
    SentEmail: Model representing a sent email.
    CompletionError: Base exception for module errors.
    SentMailAccessError: Raised when Sent Mail cannot be accessed.
"""

from .completion_checker import CompletionChecker
from .exceptions import CompletionError, SentMailAccessError
from .models import CompletionResult, SentEmail
from .reply_resolver import ReplyResolver

__all__ = [
    "CompletionChecker",
    "ReplyResolver",
    "CompletionResult",
    "SentEmail",
    "CompletionError",
    "SentMailAccessError",
]
