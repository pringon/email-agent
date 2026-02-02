"""
Integration test for Gmail API credentials and basic email fetching.

Run with: python -m pytest tests/test_gmail_integration.py -v
"""

import os
import pickle
from pathlib import Path

import pytest
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Gmail API scopes
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "config" / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "config" / "token.json"


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None

    # Load existing token if available
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Refresh or create new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Credentials file not found at {CREDENTIALS_PATH}. "
                    "Please download OAuth credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


class TestGmailIntegration:
    """Integration tests for Gmail API."""

    @pytest.fixture(scope="class")
    def gmail_service(self):
        """Create Gmail service once for all tests in this class."""
        return get_gmail_service()

    def test_credentials_file_exists(self):
        """Verify credentials.json exists."""
        assert CREDENTIALS_PATH.exists(), (
            f"credentials.json not found at {CREDENTIALS_PATH}"
        )

    def test_can_authenticate(self, gmail_service):
        """Verify we can authenticate with Gmail API."""
        assert gmail_service is not None

    def test_can_fetch_latest_email(self, gmail_service):
        """Fetch the latest email and verify it has content."""
        # Get list of messages (just 1)
        results = gmail_service.users().messages().list(
            userId="me",
            maxResults=1
        ).execute()

        messages = results.get("messages", [])
        assert len(messages) > 0, "No emails found in inbox"

        # Fetch the full message
        message_id = messages[0]["id"]
        message = gmail_service.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()

        # Verify message has expected fields
        assert "id" in message, "Message missing 'id' field"
        assert "threadId" in message, "Message missing 'threadId' field"
        assert "payload" in message, "Message missing 'payload' field"

        # Verify we can extract subject from headers
        headers = message["payload"].get("headers", [])
        subject = next(
            (h["value"] for h in headers if h["name"].lower() == "subject"),
            None
        )

        # Log for debugging (visible with pytest -v)
        print(f"\nLatest email ID: {message_id}")
        print(f"Subject: {subject}")

        assert message["id"] == message_id

    def test_can_fetch_email_snippet(self, gmail_service):
        """Verify email snippet (preview text) is accessible."""
        results = gmail_service.users().messages().list(
            userId="me",
            maxResults=1
        ).execute()

        messages = results.get("messages", [])
        assert len(messages) > 0

        message = gmail_service.users().messages().get(
            userId="me",
            id=messages[0]["id"],
            format="full"
        ).execute()

        snippet = message.get("snippet", "")
        assert isinstance(snippet, str), "Snippet should be a string"
        print(f"\nEmail snippet: {snippet[:100]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
