"""Exceptions for the completion checker module."""


class CompletionError(Exception):
    """Base exception for completion checker errors."""

    pass


class SentMailAccessError(CompletionError):
    """Raised when unable to access Sent Mail."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Unable to access Sent Mail: {reason}")
