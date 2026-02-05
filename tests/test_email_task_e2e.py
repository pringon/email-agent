"""End-to-end test for email task extraction pipeline.

This test fetches real emails from Gmail, extracts tasks using the LLM,
and prints the results with PII redacted.

Run locally:
    python -m pytest tests/test_email_task_e2e.py -v -s

Configure via environment variables:
    GMAIL_CREDENTIALS_PATH  - Path to OAuth credentials.json (default: config/credentials.json)
    GMAIL_TOKEN_PATH        - Path to OAuth token.json (default: config/token.json)
    GMAIL_NON_INTERACTIVE   - Set to "1" to fail fast if re-auth needed (for CI)
    OPENAI_API_KEY          - Required for LLM analysis

CI setup:
    1. Create a dedicated test Gmail account
    2. Generate OAuth credentials and token locally
    3. Store credentials/token as base64-encoded GitHub secrets
    4. Decode secrets to files in CI workflow before running tests

See docs/testing.md for detailed setup instructions.
"""

import os
from typing import Any

import pytest
from dotenv import load_dotenv

from src.analyzer import EmailAnalyzer, AnalysisResult, OpenAIAdapter, Message, MessageRole
from src.fetcher import EmailFetcher

# Load environment variables
load_dotenv()


def redact_pii(adapter: OpenAIAdapter, data: dict[str, Any]) -> dict[str, Any]:
    """Use LLM to redact PII from task/result data.

    Args:
        adapter: OpenAI adapter for LLM calls
        data: Dictionary containing task or result data

    Returns:
        Dictionary with PII redacted
    """
    import json

    system_prompt = """You are a PII redaction assistant. Given JSON data, redact any personally identifiable information (PII) including:
- Email addresses (replace with [EMAIL])
- Phone numbers (replace with [PHONE])
- Full names of real people (replace with [NAME])
- Physical addresses (replace with [ADDRESS])
- Company/organization names that could identify someone (replace with [ORG])
- Dates that could identify specific events (keep relative dates like "Friday" but redact specific dates like "January 15, 2024" to [DATE])
- Any other identifying information

Keep the JSON structure intact. Only modify the values that contain PII.
Return ONLY the redacted JSON, no explanation."""

    user_prompt = f"Redact PII from this JSON:\n\n{json.dumps(data, indent=2, default=str)}"

    messages = [
        Message(role=MessageRole.SYSTEM, content=system_prompt),
        Message(role=MessageRole.USER, content=user_prompt),
    ]

    response = adapter.complete(messages, temperature=0.0, json_mode=True)
    return json.loads(response)


def format_result_for_display(result: AnalysisResult) -> dict[str, Any]:
    """Convert AnalysisResult to a display-friendly dictionary."""
    return {
        "email_id": result.email_id[:8] + "...",  # Truncate for readability
        "sender": result.sender_name,
        "summary": result.summary,
        "requires_response": result.requires_response,
        "tasks": [
            {
                "title": task.title,
                "description": task.description,
                "priority": task.priority.value,
                "due_date": str(task.due_date) if task.due_date else None,
                "confidence": task.confidence,
            }
            for task in result.tasks
        ],
    }


@pytest.mark.integration
class TestEmailTaskE2E:
    """End-to-end tests for the email-to-task pipeline."""

    @pytest.fixture
    def fetcher(self):
        """Create an EmailFetcher with default settings."""
        return EmailFetcher()

    @pytest.fixture
    def analyzer(self):
        """Create an EmailAnalyzer with real OpenAI connection."""
        return EmailAnalyzer()

    @pytest.fixture
    def pii_adapter(self):
        """Create a separate adapter for PII redaction."""
        return OpenAIAdapter()

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    def test_fetch_and_extract_tasks_from_latest_emails(
        self, fetcher, analyzer, pii_adapter
    ):
        """Fetch last 20 emails, extract tasks, and print with PII redacted."""
        print("\n" + "=" * 60)
        print("EMAIL TASK EXTRACTION E2E TEST")
        print("=" * 60)

        # Fetch the last 20 emails
        print("\nFetching last 20 emails from Gmail...")
        emails = list(fetcher.fetch_latest(max_results=20))
        print(f"Fetched {len(emails)} emails")

        if not emails:
            pytest.skip("No emails found in inbox")

        # Analyze each email and collect results
        all_results: list[AnalysisResult] = []
        total_tasks = 0

        print("\nAnalyzing emails for tasks...")
        for i, email in enumerate(emails, 1):
            print(f"  [{i}/{len(emails)}] Analyzing: {email.subject[:50]}...")
            try:
                result = analyzer.analyze(email)
                all_results.append(result)
                total_tasks += len(result.tasks)
            except Exception as e:
                print(f"    Error analyzing email: {e}")
                continue

        print(f"\nAnalysis complete. Found {total_tasks} tasks across {len(emails)} emails.")

        # Print results with PII redacted
        print("\n" + "-" * 60)
        print("EXTRACTED TASKS (PII REDACTED)")
        print("-" * 60)

        emails_with_tasks = [r for r in all_results if r.tasks]

        if not emails_with_tasks:
            print("\nNo tasks extracted from any emails.")
            print("This could mean all emails were informational/FYI messages.")
        else:
            for result in emails_with_tasks:
                # Convert to display format
                display_data = format_result_for_display(result)

                # Redact PII using LLM
                try:
                    redacted_data = redact_pii(pii_adapter, display_data)
                except Exception as e:
                    print(f"\nError redacting PII: {e}")
                    redacted_data = display_data  # Fall back to original

                # Print the redacted result
                print(f"\n{'='*40}")
                print(f"Email: {redacted_data.get('email_id', 'N/A')}")
                print(f"From: {redacted_data.get('sender', 'N/A')}")
                print(f"Summary: {redacted_data.get('summary', 'N/A')}")
                print(f"Requires Response: {redacted_data.get('requires_response', False)}")

                tasks = redacted_data.get("tasks", [])
                if tasks:
                    print(f"\nTasks ({len(tasks)}):")
                    for j, task in enumerate(tasks, 1):
                        print(f"  {j}. {task.get('title', 'N/A')}")
                        print(f"     Priority: {task.get('priority', 'N/A')}")
                        if task.get("due_date"):
                            print(f"     Due: {task.get('due_date')}")
                        if task.get("description"):
                            desc = task.get("description", "")
                            if len(desc) > 100:
                                desc = desc[:100] + "..."
                            print(f"     Description: {desc}")

        # Summary statistics
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total emails analyzed: {len(all_results)}")
        print(f"Emails with tasks: {len(emails_with_tasks)}")
        print(f"Total tasks extracted: {total_tasks}")

        emails_requiring_response = sum(1 for r in all_results if r.requires_response)
        print(f"Emails requiring response: {emails_requiring_response}")

        # Assert basic expectations
        assert len(emails) > 0, "Should have fetched at least one email"
        assert len(all_results) > 0, "Should have analyzed at least one email"

        print("\nTest completed successfully!")
