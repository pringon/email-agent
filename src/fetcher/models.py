"""Email data model for the fetcher module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Email:
    """Structured email data for downstream processing.

    Attributes:
        id: Gmail message ID (unique per message)
        thread_id: Gmail thread ID (shared by messages in same thread)
        subject: Email subject line
        sender: Sender display name (or email if no name)
        sender_email: Sender email address
        recipient: Recipient email address
        date: Parsed datetime of when email was sent
        body: Plain text body content
        html_body: HTML body content (if available)
        snippet: Gmail's preview snippet
        labels: List of Gmail label IDs
        is_unread: Whether the email is marked as unread
    """

    id: str
    thread_id: str
    subject: str
    sender: str
    sender_email: str
    recipient: str
    date: datetime
    body: str
    html_body: Optional[str] = None
    snippet: str = ""
    labels: list[str] = field(default_factory=list)
    is_unread: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize email to dictionary for storage or transmission."""
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "subject": self.subject,
            "sender": self.sender,
            "sender_email": self.sender_email,
            "recipient": self.recipient,
            "date": self.date.isoformat(),
            "body": self.body,
            "html_body": self.html_body,
            "snippet": self.snippet,
            "labels": self.labels,
            "is_unread": self.is_unread,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Email":
        """Deserialize email from dictionary."""
        return cls(
            id=data["id"],
            thread_id=data["thread_id"],
            subject=data["subject"],
            sender=data["sender"],
            sender_email=data["sender_email"],
            recipient=data["recipient"],
            date=datetime.fromisoformat(data["date"]),
            body=data["body"],
            html_body=data.get("html_body"),
            snippet=data.get("snippet", ""),
            labels=data.get("labels", []),
            is_unread=data.get("is_unread", True),
        )
