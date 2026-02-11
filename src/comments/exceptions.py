"""Exceptions for the comment interpreter module."""


class CommentError(Exception):
    """Base exception for comment interpreter errors."""

    pass


class CommentParseError(CommentError):
    """Raised when a comment line cannot be parsed into a valid command."""

    def __init__(self, line: str, reason: str):
        self.line = line
        self.reason = reason
        super().__init__(f"Failed to parse comment '{line}': {reason}")


class CommentExecutionError(CommentError):
    """Raised when a parsed command cannot be executed against a task."""

    def __init__(self, command_type: str, task_id: str, reason: str):
        self.command_type = command_type
        self.task_id = task_id
        self.reason = reason
        super().__init__(
            f"Failed to execute '{command_type}' on task '{task_id}': {reason}"
        )
