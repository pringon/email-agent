"""Data models for the comment interpreter module."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CommandType(Enum):
    """Types of user commands that can be parsed from task notes."""

    PRIORITY = "priority"
    DUE = "due"
    SNOOZE = "snooze"
    IGNORE = "ignore"
    DELETE = "delete"
    NOTE = "note"
    RESPOND = "respond"


@dataclass
class ParsedCommand:
    """A command parsed from a task's notes field.

    Attributes:
        command_type: The type of command.
        raw_text: The original line of text that was parsed.
        arguments: The argument string after the command keyword.
    """

    command_type: CommandType
    raw_text: str
    arguments: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "command_type": self.command_type.value,
            "raw_text": self.raw_text,
            "arguments": self.arguments,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParsedCommand":
        """Deserialize from dictionary."""
        return cls(
            command_type=CommandType(data["command_type"]),
            raw_text=data["raw_text"],
            arguments=data.get("arguments", ""),
        )


@dataclass
class CommandResult:
    """Result of executing a single command on a task.

    Attributes:
        task_id: ID of the task that was processed.
        task_title: Title of the task.
        command: The ParsedCommand that was executed.
        success: Whether the command executed successfully.
        action_taken: Description of what was done.
        error: Error message if the command failed.
    """

    task_id: str
    task_title: str
    command: ParsedCommand
    success: bool
    action_taken: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "task_id": self.task_id,
            "task_title": self.task_title,
            "command": self.command.to_dict(),
            "success": self.success,
            "action_taken": self.action_taken,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommandResult":
        """Deserialize from dictionary."""
        return cls(
            task_id=data["task_id"],
            task_title=data["task_title"],
            command=ParsedCommand.from_dict(data["command"]),
            success=data["success"],
            action_taken=data.get("action_taken", ""),
            error=data.get("error", ""),
        )


@dataclass
class ProcessingResult:
    """Aggregate result of processing comments across all tasks.

    Attributes:
        processed_at: When processing was performed.
        tasks_scanned: Number of tasks scanned for comments.
        commands_found: Number of commands parsed across all tasks.
        commands_executed: Number of commands successfully executed.
        results: Per-command results.
        errors: Global errors (e.g., failure to list tasks).
    """

    processed_at: datetime = field(default_factory=datetime.now)
    tasks_scanned: int = 0
    commands_found: int = 0
    commands_executed: int = 0
    results: list[CommandResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Record a global error."""
        self.errors.append(error)

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.errors) > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "processed_at": self.processed_at.isoformat(),
            "tasks_scanned": self.tasks_scanned,
            "commands_found": self.commands_found,
            "commands_executed": self.commands_executed,
            "results": [r.to_dict() for r in self.results],
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcessingResult":
        """Deserialize from dictionary."""
        return cls(
            processed_at=datetime.fromisoformat(data["processed_at"]),
            tasks_scanned=data.get("tasks_scanned", 0),
            commands_found=data.get("commands_found", 0),
            commands_executed=data.get("commands_executed", 0),
            results=[CommandResult.from_dict(r) for r in data.get("results", [])],
            errors=data.get("errors", []),
        )
