"""Data models for the completion checker module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class SentEmail:
    """Represents a sent email for completion checking.

    A lightweight model containing only the fields needed for
    matching sent replies to existing task threads.

    Attributes:
        id: Gmail message ID.
        thread_id: Gmail thread ID for matching with tasks.
        subject: Email subject line.
        recipient: Recipient email address.
        date: When the email was sent.
        snippet: Brief preview of the message content.
    """

    id: str
    thread_id: str
    subject: str
    recipient: str
    date: datetime
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "subject": self.subject,
            "recipient": self.recipient,
            "date": self.date.isoformat(),
            "snippet": self.snippet,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SentEmail":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            thread_id=data["thread_id"],
            subject=data["subject"],
            recipient=data["recipient"],
            date=datetime.fromisoformat(data["date"]),
            snippet=data.get("snippet", ""),
        )


@dataclass
class CompletionResult:
    """Result of a completion check operation.

    Tracks what was scanned and which tasks were completed.

    Attributes:
        sent_emails_scanned: Number of sent emails checked.
        threads_matched: Number of threads that had associated tasks.
        tasks_completed: List of task IDs that were marked complete.
        thread_task_map: Mapping of thread_id to list of completed task IDs.
        checked_at: Timestamp of when the check was performed.
        errors: Any errors encountered during processing.
    """

    sent_emails_scanned: int = 0
    threads_matched: int = 0
    tasks_completed: list[str] = field(default_factory=list)
    thread_task_map: dict[str, list[str]] = field(default_factory=dict)
    checked_at: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "sent_emails_scanned": self.sent_emails_scanned,
            "threads_matched": self.threads_matched,
            "tasks_completed": self.tasks_completed,
            "thread_task_map": self.thread_task_map,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompletionResult":
        """Deserialize from dictionary."""
        checked_at = None
        if data.get("checked_at"):
            checked_at = datetime.fromisoformat(data["checked_at"])
        return cls(
            sent_emails_scanned=data.get("sent_emails_scanned", 0),
            threads_matched=data.get("threads_matched", 0),
            tasks_completed=data.get("tasks_completed", []),
            thread_task_map=data.get("thread_task_map", {}),
            checked_at=checked_at,
            errors=data.get("errors", []),
        )

    @property
    def total_completed(self) -> int:
        """Total number of tasks completed."""
        return len(self.tasks_completed)

    def add_completed_tasks(self, thread_id: str, task_ids: list[str]) -> None:
        """Record tasks completed for a thread.

        Args:
            thread_id: Gmail thread ID that was replied to.
            task_ids: List of task IDs that were marked complete.
        """
        if task_ids:
            self.thread_task_map[thread_id] = task_ids
            self.tasks_completed.extend(task_ids)
            self.threads_matched += 1

    def add_error(self, error: str) -> None:
        """Record an error that occurred during processing."""
        self.errors.append(error)
