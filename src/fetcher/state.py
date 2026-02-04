"""State repository interfaces for tracking processed emails."""

from abc import ABC, abstractmethod
from typing import Set


class StateRepository(ABC):
    """Interface for tracking processed emails by message ID.

    Implementations can use different backends:
    - InMemoryStateRepository: For testing, treats all emails as new
    - TaskBackedStateRepository (future): Queries Google Tasks metadata
    """

    @abstractmethod
    def is_processed(self, message_id: str) -> bool:
        """Check if email message has been processed.

        Args:
            message_id: Gmail message ID

        Returns:
            True if this message has already been processed
        """
        pass

    @abstractmethod
    def mark_processed(self, message_id: str) -> None:
        """Mark email message as processed.

        Args:
            message_id: Gmail message ID
        """
        pass

    @abstractmethod
    def get_processed_ids(self) -> Set[str]:
        """Get all processed message IDs.

        Returns:
            Set of processed Gmail message IDs
        """
        pass


class InMemoryStateRepository(StateRepository):
    """In-memory implementation for testing and initial development.

    This implementation keeps processed IDs in memory, meaning all
    emails appear as new on each application restart. This is useful
    for testing but not for production cronjob scenarios.

    For production use, implement TaskBackedStateRepository that
    queries Google Tasks metadata to determine processed status.
    """

    def __init__(self) -> None:
        """Initialize empty processed set."""
        self._processed: Set[str] = set()

    def is_processed(self, message_id: str) -> bool:
        """Check if email message has been processed."""
        return message_id in self._processed

    def mark_processed(self, message_id: str) -> None:
        """Mark email message as processed."""
        self._processed.add(message_id)

    def get_processed_ids(self) -> Set[str]:
        """Get all processed message IDs."""
        return self._processed.copy()

    def clear(self) -> None:
        """Clear all processed IDs. Useful for testing."""
        self._processed.clear()
