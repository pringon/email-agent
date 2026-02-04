"""Email fetcher module for retrieving emails from Gmail.

This module provides the EmailFetcher class and supporting components
for fetching and parsing emails from the Gmail API.

Public API:
    - EmailFetcher: Main class for fetching emails
    - Email: Structured email data model
    - GmailAuthenticator: Authentication helper
    - StateRepository: Interface for tracking processed emails
    - InMemoryStateRepository: In-memory implementation
"""

from .email_fetcher import EmailFetcher
from .gmail_auth import GmailAuthenticator
from .models import Email
from .state import InMemoryStateRepository, StateRepository

__all__ = [
    "EmailFetcher",
    "Email",
    "GmailAuthenticator",
    "StateRepository",
    "InMemoryStateRepository",
]
