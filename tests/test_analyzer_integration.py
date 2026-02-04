"""Integration tests for EmailAnalyzer with real OpenAI API."""

import os
from datetime import datetime

import pytest
from dotenv import load_dotenv

from src.analyzer import EmailAnalyzer, Priority
from src.fetcher import Email

# Load environment variables
load_dotenv()


@pytest.mark.integration
class TestOpenAIIntegration:
    """Tests that require actual OpenAI API access."""

    @pytest.fixture
    def analyzer(self):
        """Create an EmailAnalyzer with real OpenAI connection."""
        return EmailAnalyzer()

    @pytest.fixture
    def email_with_task(self):
        """Email that should extract a task."""
        return Email(
            id="test-msg-001",
            thread_id="test-thread-001",
            subject="Q1 Report Review - Please respond by Friday",
            sender="Alice Johnson",
            sender_email="alice@example.com",
            recipient="me@example.com",
            date=datetime(2024, 1, 15, 9, 30),
            body="""Hi,

I've attached the Q1 financial report for your review.

Could you please review it and send me your feedback by this Friday (January 19th)?
This is urgent as we need to present it to the board next Monday.

Thanks,
Alice""",
        )

    @pytest.fixture
    def email_without_task(self):
        """Email that should not extract any tasks."""
        return Email(
            id="test-msg-002",
            thread_id="test-thread-002",
            subject="FYI: Office will be closed on Monday",
            sender="HR Department",
            sender_email="hr@example.com",
            recipient="all@example.com",
            date=datetime(2024, 1, 15, 14, 0),
            body="""Hi everyone,

Just a reminder that the office will be closed on Monday, January 22nd
for the Martin Luther King Jr. holiday.

Enjoy your long weekend!

HR Team""",
        )

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    def test_analyze_email_with_task(self, analyzer, email_with_task):
        """Test analyzing an email that contains an actionable task."""
        result = analyzer.analyze(email_with_task)

        # Verify basic structure
        assert result.email_id == "test-msg-001"
        assert result.thread_id == "test-thread-001"
        assert result.summary  # Should have a summary
        assert len(result.summary) > 10  # Summary should be meaningful

        # Should extract at least one task
        assert len(result.tasks) >= 1

        # Verify task properties
        task = result.tasks[0]
        assert task.title  # Should have a title
        assert task.source_email_id == "test-msg-001"
        assert task.source_thread_id == "test-thread-001"
        assert task.priority in [Priority.HIGH, Priority.URGENT]  # Should recognize urgency

        # Should recognize it requires a response
        assert result.requires_response is True

        print(f"\n--- Analysis Result ---")
        print(f"Summary: {result.summary}")
        print(f"Requires response: {result.requires_response}")
        print(f"Tasks extracted: {len(result.tasks)}")
        for i, t in enumerate(result.tasks, 1):
            print(f"  {i}. {t.title} (Priority: {t.priority.value}, Due: {t.due_date})")

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    def test_analyze_email_without_task(self, analyzer, email_without_task):
        """Test analyzing an informational email with no tasks."""
        result = analyzer.analyze(email_without_task)

        # Verify basic structure
        assert result.email_id == "test-msg-002"
        assert result.summary  # Should still have a summary

        # Should have no tasks (or possibly low-priority FYI task)
        # Being lenient here as LLM might interpret "remember office is closed" as a task
        if result.tasks:
            # If any task extracted, it should be low priority
            assert all(t.priority in [Priority.LOW, Priority.MEDIUM] for t in result.tasks)

        # Should not require a response
        assert result.requires_response is False

        print(f"\n--- Analysis Result ---")
        print(f"Summary: {result.summary}")
        print(f"Requires response: {result.requires_response}")
        print(f"Tasks extracted: {len(result.tasks)}")

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    def test_analyze_email_with_multiple_tasks(self, analyzer):
        """Test analyzing an email with multiple action items."""
        email = Email(
            id="test-msg-003",
            thread_id="test-thread-003",
            subject="Action items from today's meeting",
            sender="Project Manager",
            sender_email="pm@example.com",
            recipient="team@example.com",
            date=datetime(2024, 1, 15, 16, 0),
            body="""Hi team,

Here are the action items from today's meeting:

1. John - Update the database schema by Wednesday
2. Sarah - Review the API documentation by Thursday
3. Mike - Schedule the client demo for next week

Please confirm once you've completed your items.

Thanks,
PM""",
        )

        result = analyzer.analyze(email)

        # Should extract multiple tasks
        assert len(result.tasks) >= 2  # At least 2 tasks

        print(f"\n--- Analysis Result ---")
        print(f"Summary: {result.summary}")
        print(f"Tasks extracted: {len(result.tasks)}")
        for i, t in enumerate(result.tasks, 1):
            print(f"  {i}. {t.title} (Priority: {t.priority.value}, Due: {t.due_date})")
