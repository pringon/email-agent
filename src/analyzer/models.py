"""Data models for the analyzer module."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional


class Priority(Enum):
    """Task priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class MessageRole(Enum):
    """LLM message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """A message in an LLM conversation.

    Attributes:
        role: The role of the message sender (system, user, assistant).
        content: The text content of the message.
    """

    role: MessageRole
    content: str

    def to_dict(self) -> dict[str, str]:
        """Serialize message to dictionary for API calls."""
        return {
            "role": self.role.value,
            "content": self.content,
        }


@dataclass
class ExtractedTask:
    """A task extracted from an email by the LLM.

    Attributes:
        title: Short, actionable task title.
        description: Longer description with context from email.
        priority: Task priority level.
        source_email_id: Gmail message ID this task came from.
        source_thread_id: Gmail thread ID for linking.
        due_date: Optional deadline extracted from email.
        confidence: LLM's confidence in this extraction (0.0-1.0).
    """

    title: str
    description: str
    priority: Priority
    source_email_id: str
    source_thread_id: str
    due_date: Optional[date] = None
    confidence: float = 1.0
    source_email_subject: str = ""
    source_sender: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize task to dictionary for storage."""
        return {
            "title": self.title,
            "description": self.description,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "priority": self.priority.value,
            "source_email_id": self.source_email_id,
            "source_thread_id": self.source_thread_id,
            "confidence": self.confidence,
            "source_email_subject": self.source_email_subject,
            "source_sender": self.source_sender,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractedTask":
        """Deserialize task from dictionary.

        Args:
            data: Dictionary containing task fields.

        Returns:
            ExtractedTask instance.
        """
        return cls(
            title=data["title"],
            description=data["description"],
            due_date=date.fromisoformat(data["due_date"]) if data.get("due_date") else None,
            priority=Priority(data["priority"]),
            source_email_id=data["source_email_id"],
            source_thread_id=data["source_thread_id"],
            confidence=data.get("confidence", 1.0),
            source_email_subject=data.get("source_email_subject", ""),
            source_sender=data.get("source_sender", ""),
        )


@dataclass
class AnalysisResult:
    """Complete analysis result for an email.

    Attributes:
        email_id: Gmail message ID that was analyzed.
        thread_id: Gmail thread ID.
        summary: Brief summary of the email content.
        tasks: List of extracted tasks (may be empty).
        requires_response: Whether email needs a reply.
        sender_name: Extracted sender name for context.
        raw_response: Original LLM response for debugging.
    """

    email_id: str
    thread_id: str
    summary: str
    tasks: list[ExtractedTask] = field(default_factory=list)
    requires_response: bool = False
    sender_name: str = ""
    raw_response: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "email_id": self.email_id,
            "thread_id": self.thread_id,
            "summary": self.summary,
            "tasks": [t.to_dict() for t in self.tasks],
            "requires_response": self.requires_response,
            "sender_name": self.sender_name,
            "raw_response": self.raw_response,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisResult":
        """Deserialize result from dictionary.

        Args:
            data: Dictionary containing result fields.

        Returns:
            AnalysisResult instance.
        """
        return cls(
            email_id=data["email_id"],
            thread_id=data["thread_id"],
            summary=data["summary"],
            tasks=[ExtractedTask.from_dict(t) for t in data.get("tasks", [])],
            requires_response=data.get("requires_response", False),
            sender_name=data.get("sender_name", ""),
            raw_response=data.get("raw_response"),
        )
