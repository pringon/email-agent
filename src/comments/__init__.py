"""Comment interpreter module for parsing user task instructions.

This module scans Google Task notes for @commands and executes
them against tasks via TaskManager.

Public API:
    CommentInterpreter: Main class for parsing and executing comments.
    CommandType: Enum of supported command types.
    ParsedCommand: A single parsed command from notes.
    CommandResult: Result of executing one command.
    ProcessingResult: Aggregate result across all tasks.
    CommentError: Base exception for module errors.
    CommentParseError: Raised on parse failures.
    CommentExecutionError: Raised on execution failures.
"""

from .comment_interpreter import CommentInterpreter
from .exceptions import CommentError, CommentExecutionError, CommentParseError
from .models import CommandResult, CommandType, ParsedCommand, ProcessingResult

__all__ = [
    "CommentInterpreter",
    "CommandType",
    "ParsedCommand",
    "CommandResult",
    "ProcessingResult",
    "CommentError",
    "CommentParseError",
    "CommentExecutionError",
]
