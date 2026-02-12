"""Integration tests for ReplyResolver with real OpenAI API.

Tests the LLM-based task resolution with actual API calls to verify
that the prompts produce correct, parseable responses.

Run locally:
    OPENAI_API_KEY=sk-... python -m pytest tests/test_reply_resolver_integration.py -v -s
"""

import os

import pytest
from dotenv import load_dotenv

from src.completion.reply_resolver import ReplyResolver
from src.tasks.models import Task

# Load environment variables
load_dotenv()


@pytest.mark.integration
class TestReplyResolverIntegration:
    """Tests that require actual OpenAI API access."""

    @pytest.fixture
    def resolver(self):
        """Create a ReplyResolver with real OpenAI connection."""
        return ReplyResolver()

    @pytest.fixture
    def tasks_from_meeting_email(self):
        """Tasks extracted from a meeting action-items email."""
        return [
            Task(
                id="task-review",
                title="Review Q1 proposal and send feedback",
                notes="Priority: high\n\nReview the Q1 proposal document and reply with feedback",
            ),
            Task(
                id="task-schedule",
                title="Schedule follow-up meeting with Sarah",
                notes="Priority: medium\n\nSet up a 30-min sync to discuss project timeline",
            ),
            Task(
                id="task-budget",
                title="Update budget spreadsheet with Q2 projections",
                notes="Priority: low\n\nAdd Q2 projections to the shared budget sheet",
            ),
        ]

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    def test_resolve_reply_addressing_one_task(self, resolver, tasks_from_meeting_email):
        """Reply that clearly addresses one specific task."""
        reply_body = (
            "Hi Alice,\n\n"
            "I've reviewed the Q1 proposal. Overall it looks solid — I left "
            "detailed comments in the doc. The revenue projections in section 3 "
            "need a second look, but otherwise I think we're good to go.\n\n"
            "Best,\nDan"
        )

        result = resolver.resolve(
            reply_body=reply_body,
            subject="Re: Action items from Monday's meeting",
            tasks=tasks_from_meeting_email,
        )

        assert "task-review" in result, (
            f"Expected 'task-review' to be resolved, got: {result}"
        )
        # The other tasks should NOT be resolved by this reply
        assert "task-schedule" not in result
        assert "task-budget" not in result

        print(f"\nResolved task IDs: {result}")

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    def test_resolve_reply_addressing_no_tasks(self, resolver, tasks_from_meeting_email):
        """Generic acknowledgement reply that doesn't address any task."""
        reply_body = (
            "Thanks for the update! Talk soon.\n\n"
            "Sent from my phone"
        )

        result = resolver.resolve(
            reply_body=reply_body,
            subject="Re: Action items from Monday's meeting",
            tasks=tasks_from_meeting_email,
        )

        assert result == [], (
            f"Expected no tasks resolved for generic reply, got: {result}"
        )

        print(f"\nResolved task IDs: {result}")

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    def test_resolve_reply_addressing_multiple_tasks(self, resolver, tasks_from_meeting_email):
        """Reply that addresses multiple tasks at once."""
        reply_body = (
            "Hi team,\n\n"
            "Quick update on my action items:\n"
            "- I've gone through the Q1 proposal and left my comments. LGTM.\n"
            "- I've also updated the budget spreadsheet with Q2 projections, "
            "see the 'Q2 Forecast' tab.\n\n"
            "Still need to find a time with Sarah for the follow-up — will "
            "send a calendar invite tomorrow.\n\n"
            "Dan"
        )

        result = resolver.resolve(
            reply_body=reply_body,
            subject="Re: Action items from Monday's meeting",
            tasks=tasks_from_meeting_email,
        )

        assert "task-review" in result, (
            f"Expected 'task-review' resolved, got: {result}"
        )
        assert "task-budget" in result, (
            f"Expected 'task-budget' resolved, got: {result}"
        )
        # The meeting scheduling is explicitly deferred, not completed
        assert "task-schedule" not in result, (
            f"Expected 'task-schedule' NOT resolved (deferred), got: {result}"
        )

        print(f"\nResolved task IDs: {result}")

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    def test_resolve_returns_valid_task_ids(self, resolver, tasks_from_meeting_email):
        """Resolved IDs are always a subset of the input task IDs."""
        reply_body = "I've handled everything on my plate. All done!"

        result = resolver.resolve(
            reply_body=reply_body,
            subject="Re: Action items",
            tasks=tasks_from_meeting_email,
        )

        valid_ids = {t.id for t in tasks_from_meeting_email}
        assert all(tid in valid_ids for tid in result), (
            f"Got invalid task ID(s): {set(result) - valid_ids}"
        )

        print(f"\nResolved task IDs: {result}")
