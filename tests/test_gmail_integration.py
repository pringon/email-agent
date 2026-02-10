"""
Integration test for Gmail API credentials and basic email fetching.

Run with: python -m pytest tests/test_gmail_integration.py -v

Configure via environment variables:
    GMAIL_CREDENTIALS_PATH  - Path to OAuth credentials.json
    GMAIL_TOKEN_PATH        - Path to OAuth token.json
    GMAIL_NON_INTERACTIVE   - Set to "1" to fail fast if re-auth needed
"""

from pathlib import Path

import pytest

from src.fetcher import GmailAuthenticator

# Paths (for test_credentials_file_exists only)
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CREDENTIALS_PATH = PROJECT_ROOT / "config" / "credentials.json"


@pytest.mark.integration
class TestGmailIntegration:
    """Integration tests for Gmail API."""

    @pytest.fixture(scope="class")
    def gmail_service(self):
        """Create Gmail service using GmailAuthenticator."""
        auth = GmailAuthenticator()
        return auth.get_service()

    def test_credentials_file_exists(self):
        """Verify credentials.json exists at the default location."""
        assert DEFAULT_CREDENTIALS_PATH.exists(), (
            f"credentials.json not found at {DEFAULT_CREDENTIALS_PATH}"
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
