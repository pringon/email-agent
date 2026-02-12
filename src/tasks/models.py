"""Data models for the tasks module."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    """Google Tasks status values."""

    NEEDS_ACTION = "needsAction"
    COMPLETED = "completed"


@dataclass
class TaskList:
    """Represents a Google Tasks list.

    Attributes:
        id: Unique identifier for the task list.
        title: Human-readable title of the list.
        updated: When the list was last modified.
    """

    id: str
    title: str
    updated: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskList":
        """Deserialize from dictionary."""
        updated = None
        if data.get("updated"):
            updated = datetime.fromisoformat(data["updated"].replace("Z", "+00:00"))
        return cls(
            id=data["id"],
            title=data["title"],
            updated=updated,
        )

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "TaskList":
        """Create from Google Tasks API response."""
        updated = None
        if data.get("updated"):
            # Google API returns RFC 3339 format
            updated = datetime.fromisoformat(data["updated"].replace("Z", "+00:00"))
        return cls(
            id=data["id"],
            title=data["title"],
            updated=updated,
        )


@dataclass
class Task:
    """Represents a Google Task with email metadata.

    Attributes:
        id: Unique identifier from Google Tasks (None for new tasks).
        title: Task title (max 1024 chars in Google Tasks).
        notes: Task notes/description with email context.
        status: Current task status.
        due: Optional due date.
        completed: When the task was completed (if applicable).
        source_email_id: Gmail message ID that generated this task.
        source_thread_id: Gmail thread ID for reply detection.
        task_list_id: ID of the task list this task belongs to.
        position: Position in the task list (set by API).
        parent: Parent task ID for subtasks.
        etag: ETag for optimistic concurrency.
    """

    title: str
    id: Optional[str] = None
    notes: Optional[str] = None
    status: TaskStatus = TaskStatus.NEEDS_ACTION
    due: Optional[date] = None
    completed: Optional[datetime] = None
    source_email_id: Optional[str] = None
    source_thread_id: Optional[str] = None
    source_email_subject: Optional[str] = None
    source_sender: Optional[str] = None
    task_list_id: Optional[str] = None
    position: Optional[str] = None
    parent: Optional[str] = None
    etag: Optional[str] = None

    # Metadata prefix used in task notes to store email linking info
    METADATA_PREFIX = "---email-agent-metadata---"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "id": self.id,
            "title": self.title,
            "notes": self.notes,
            "status": self.status.value,
            "due": self.due.isoformat() if self.due else None,
            "completed": self.completed.isoformat() if self.completed else None,
            "source_email_id": self.source_email_id,
            "source_thread_id": self.source_thread_id,
            "source_email_subject": self.source_email_subject,
            "source_sender": self.source_sender,
            "task_list_id": self.task_list_id,
            "position": self.position,
            "parent": self.parent,
            "etag": self.etag,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Deserialize from dictionary."""
        due = None
        if data.get("due"):
            due = date.fromisoformat(data["due"])

        completed = None
        if data.get("completed"):
            completed = datetime.fromisoformat(data["completed"])

        return cls(
            id=data.get("id"),
            title=data["title"],
            notes=data.get("notes"),
            status=TaskStatus(data.get("status", "needsAction")),
            due=due,
            completed=completed,
            source_email_id=data.get("source_email_id"),
            source_thread_id=data.get("source_thread_id"),
            source_email_subject=data.get("source_email_subject"),
            source_sender=data.get("source_sender"),
            task_list_id=data.get("task_list_id"),
            position=data.get("position"),
            parent=data.get("parent"),
            etag=data.get("etag"),
        )

    def to_api_body(self) -> dict[str, Any]:
        """Convert to Google Tasks API request body.

        Embeds email metadata in the notes field for later retrieval.
        """
        body: dict[str, Any] = {
            "title": self.title[:1024],  # API limit
            "status": self.status.value,
        }

        # Include ID for update operations (required by Tasks API PUT)
        if self.id:
            body["id"] = self.id

        # Build notes with embedded metadata
        notes_parts = []
        if self.notes:
            notes_parts.append(self.notes)

        # Embed email metadata in notes
        if self.source_email_id or self.source_thread_id:
            metadata_lines = [self.METADATA_PREFIX]
            if self.source_email_id:
                metadata_lines.append(f"email_id:{self.source_email_id}")
            if self.source_thread_id:
                metadata_lines.append(f"thread_id:{self.source_thread_id}")
            if self.source_email_subject:
                metadata_lines.append(f"email_subject:{self.source_email_subject}")
            if self.source_sender:
                metadata_lines.append(f"sender:{self.source_sender}")
            notes_parts.append("\n".join(metadata_lines))

        if notes_parts:
            body["notes"] = "\n\n".join(notes_parts)

        if self.due:
            # Google Tasks expects RFC 3339 date-time for due
            body["due"] = f"{self.due.isoformat()}T00:00:00.000Z"

        if self.parent:
            body["parent"] = self.parent

        return body

    @classmethod
    def from_api_response(cls, data: dict[str, Any], task_list_id: Optional[str] = None) -> "Task":
        """Create from Google Tasks API response.

        Extracts email metadata from notes field if present.
        """
        # Parse due date
        due = None
        if data.get("due"):
            # API returns RFC 3339, extract just the date part
            due_str = data["due"].split("T")[0]
            due = date.fromisoformat(due_str)

        # Parse completed datetime
        completed = None
        if data.get("completed"):
            completed = datetime.fromisoformat(data["completed"].replace("Z", "+00:00"))

        # Extract metadata from notes
        source_email_id = None
        source_thread_id = None
        source_email_subject = None
        source_sender = None
        notes = data.get("notes", "")
        clean_notes = notes

        if cls.METADATA_PREFIX in notes:
            parts = notes.split(cls.METADATA_PREFIX)
            clean_notes = parts[0].rstrip()
            if len(parts) > 1:
                metadata_section = parts[1]
                for line in metadata_section.strip().split("\n"):
                    if line.startswith("email_id:"):
                        source_email_id = line[9:].strip()
                    elif line.startswith("thread_id:"):
                        source_thread_id = line[10:].strip()
                    elif line.startswith("email_subject:"):
                        source_email_subject = line[14:].strip()
                    elif line.startswith("sender:"):
                        source_sender = line[7:].strip()

        return cls(
            id=data.get("id"),
            title=data.get("title", ""),
            notes=clean_notes if clean_notes else None,
            status=TaskStatus(data.get("status", "needsAction")),
            due=due,
            completed=completed,
            source_email_id=source_email_id,
            source_thread_id=source_thread_id,
            source_email_subject=source_email_subject,
            source_sender=source_sender,
            task_list_id=task_list_id,
            position=data.get("position"),
            parent=data.get("parent"),
            etag=data.get("etag"),
        )

    @property
    def gmail_url(self) -> Optional[str]:
        """Construct a Gmail URL to the source email thread."""
        if self.source_thread_id:
            return f"https://mail.google.com/mail/u/0/#inbox/{self.source_thread_id}"
        return None

    @property
    def is_completed(self) -> bool:
        """Check if task is marked complete."""
        return self.status == TaskStatus.COMPLETED

    def mark_completed(self) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed = datetime.now()

    def mark_incomplete(self) -> None:
        """Mark task as needing action."""
        self.status = TaskStatus.NEEDS_ACTION
        self.completed = None
