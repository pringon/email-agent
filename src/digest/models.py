"""Data models for the digest reporter module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.tasks.models import Task


@dataclass
class DigestSection:
    """A section of the digest grouping related tasks.

    Attributes:
        heading: Section title (e.g., "Overdue Tasks").
        tasks: List of Task objects in this section.
    """

    heading: str
    tasks: list[Task] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Number of tasks in this section."""
        return len(self.tasks)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "heading": self.heading,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DigestSection":
        """Deserialize from dictionary."""
        return cls(
            heading=data["heading"],
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
        )


@dataclass
class DigestReport:
    """A complete daily digest report.

    Attributes:
        generated_at: When the report was generated.
        sections: Ordered list of task sections.
        total_pending: Total number of pending tasks across all sections.
        total_overdue: Number of overdue tasks.
        task_list_name: Name of the task list this report covers.
    """

    generated_at: datetime = field(default_factory=datetime.now)
    sections: list[DigestSection] = field(default_factory=list)
    total_pending: int = 0
    total_overdue: int = 0
    task_list_name: str = ""

    @property
    def is_empty(self) -> bool:
        """Check if digest has no pending tasks."""
        return self.total_pending == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "sections": [s.to_dict() for s in self.sections],
            "total_pending": self.total_pending,
            "total_overdue": self.total_overdue,
            "task_list_name": self.task_list_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DigestReport":
        """Deserialize from dictionary."""
        return cls(
            generated_at=datetime.fromisoformat(data["generated_at"]),
            sections=[DigestSection.from_dict(s) for s in data.get("sections", [])],
            total_pending=data.get("total_pending", 0),
            total_overdue=data.get("total_overdue", 0),
            task_list_name=data.get("task_list_name", ""),
        )


@dataclass
class DeliveryResult:
    """Result of delivering a digest report.

    Attributes:
        delivered_at: When delivery was attempted.
        plain_text_output: The formatted plain text (always generated).
        email_sent: Whether the email was sent successfully.
        email_recipient: Who the email was sent to (if applicable).
        email_message_id: Gmail message ID of sent digest (if applicable).
        errors: Any errors encountered during delivery.
    """

    delivered_at: datetime = field(default_factory=datetime.now)
    plain_text_output: str = ""
    email_sent: bool = False
    email_recipient: str = ""
    email_message_id: Optional[str] = None
    errors: list[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Record an error that occurred during delivery."""
        self.errors.append(error)

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.errors) > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "delivered_at": self.delivered_at.isoformat(),
            "plain_text_output": self.plain_text_output,
            "email_sent": self.email_sent,
            "email_recipient": self.email_recipient,
            "email_message_id": self.email_message_id,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeliveryResult":
        """Deserialize from dictionary."""
        return cls(
            delivered_at=datetime.fromisoformat(data["delivered_at"]),
            plain_text_output=data.get("plain_text_output", ""),
            email_sent=data.get("email_sent", False),
            email_recipient=data.get("email_recipient", ""),
            email_message_id=data.get("email_message_id"),
            errors=data.get("errors", []),
        )
