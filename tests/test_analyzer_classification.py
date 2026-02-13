"""Integration tests for email classification accuracy.

Validates that the EmailAnalyzer correctly distinguishes actionable emails
from marketing, automated, newsletter, and informational emails.

Each test case uses a realistic mock Email object and asserts on task
extraction behavior. Add new EmailSpecimen entries to SPECIMENS to
expand coverage as new edge cases are discovered.

Run:
    python -m pytest tests/test_analyzer_classification.py -v -s

Requires:
    OPENAI_API_KEY environment variable
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pytest
from dotenv import load_dotenv

from src.analyzer import EmailAnalyzer, EmailType
from src.fetcher import Email

load_dotenv()


@dataclass
class EmailSpecimen:
    """A test email with expected classification behavior."""

    name: str
    category: str  # marketing, automated, newsletter, actionable, informational
    sender: str
    sender_email: str
    subject: str
    body: str
    labels: list[str] = field(default_factory=list)
    expect_tasks: bool = False
    min_tasks: int = 0
    expected_email_type: Optional[EmailType] = None


SPECIMENS: list[EmailSpecimen] = [
    # --- Marketing / Promotional ---
    EmailSpecimen(
        name="spotify_presale_promo",
        category="marketing",
        sender="Spotify",
        sender_email="no-reply@spotify.com",
        subject="A special thank you from Trinix",
        body="""\
Trinix https://open.spotify.com/artist/3HqP3nd8WI0VfHRhApPlan
Thanks for being a fan


Trinix is giving you special access to get tickets to their upcoming tour!



Presale starts now
Offer code: *origin*
Ends on 13 February 2026 at 10:00 CET



*Lisbon,PT*
2 May 2026


Get tickets ( https://spoti.fi/jubEfsoYg0b )



*Amsterdam, NL*
7 May 2026


Get tickets ( https://spoti.fi/KX0XUnp2D0b )



*London, UK*
8 May 2026


Get tickets ( https://spoti.fi/2FjniJIRg0b )



#SpotifyFansFirst

Offers for top fans. Fans First rewards loyal listeners with perks like
concert presale tickets, limited-edition merchandise, one-of-a-kind
experiences and more.

This message was sent to user@gmail.com.
Unsubscribe (https://www.spotify.com/account/unsubscribe)""",
        labels=["CATEGORY_UPDATES", "INBOX", "UNREAD"],
        expect_tasks=False,
        expected_email_type=EmailType.MARKETING,
    ),
    EmailSpecimen(
        name="amazon_deal_promo",
        category="marketing",
        sender="Amazon",
        sender_email="store-news@amazon.com",
        subject="Lightning deals just for you!",
        body="""\
Hi there,

We noticed you've been browsing electronics. Check out these limited-time deals:

- 40% off wireless earbuds
- $50 off smart home devices
- Free shipping on orders over $25

Shop now before these deals expire!

To unsubscribe, click here.""",
        labels=["CATEGORY_PROMOTIONS", "INBOX", "UNREAD"],
        expect_tasks=False,
        expected_email_type=EmailType.MARKETING,
    ),
    # --- Automated Notifications (informational, no action required) ---
    EmailSpecimen(
        name="shipping_notification",
        category="automated",
        sender="UPS",
        sender_email="auto-notify@ups.com",
        subject="Your package is on its way!",
        body="""\
Your package from Amazon is on its way!

Tracking Number: 1Z999AA10123456784
Estimated Delivery: Thursday, January 18

Track your package: https://ups.com/track/1Z999AA10123456784

This is an automated message. Please do not reply.""",
        labels=["CATEGORY_UPDATES", "INBOX", "UNREAD"],
        expect_tasks=False,
        expected_email_type=EmailType.AUTOMATED,
    ),
    # --- Newsletter / Digest ---
    EmailSpecimen(
        name="tech_newsletter",
        category="newsletter",
        sender="TechCrunch Daily",
        sender_email="newsletter@techcrunch.com",
        subject="TechCrunch Daily: AI funding hits new record",
        body="""\
Good morning! Here's your daily tech briefing:

TOP STORIES
- AI startup funding reaches $50B in 2024
- Apple announces new MacBook Pro lineup
- Google updates search algorithm

OPINION
- Why open source is winning the AI race

Read more at techcrunch.com

You're receiving this because you subscribed to TechCrunch Daily. Unsubscribe.""",
        labels=["CATEGORY_UPDATES", "INBOX", "UNREAD"],
        expect_tasks=False,
        expected_email_type=EmailType.NEWSLETTER,
    ),
    # --- Informational / FYI ---
    EmailSpecimen(
        name="team_announcement",
        category="informational",
        sender="HR Department",
        sender_email="hr@company.com",
        subject="Welcome our new team member!",
        body="""\
Hi everyone,

Please join me in welcoming Alex Rivera to the engineering team! Alex will
be starting on Monday as a Senior Backend Engineer.

Alex comes to us from BigTech Corp where they spent 5 years building
distributed systems.

Let's make Alex feel welcome!

Best,
HR Team""",
        labels=["INBOX", "UNREAD"],
        expect_tasks=False,
    ),
    # --- Legitimate Actionable Emails ---
    EmailSpecimen(
        name="github_ci_failure",
        category="actionable",
        sender="GitHub",
        sender_email="notifications@github.com",
        subject="[myorg/myrepo] Run failed: CI Pipeline - main",
        body="""\
Run failed: CI Pipeline - main

myorg/myrepo (main) — 2 failing checks

  x test-unit (3m 42s) — Process completed with exit code 1
  v lint (1m 12s) — Passed

View run: https://github.com/myorg/myrepo/actions/runs/12345

You are receiving this because you are subscribed to this thread.""",
        labels=["CATEGORY_UPDATES", "INBOX", "UNREAD"],
        expect_tasks=True,
        min_tasks=1,
    ),
    EmailSpecimen(
        name="meeting_request",
        category="actionable",
        sender="Sarah Chen",
        sender_email="sarah.chen@company.com",
        subject="Can we meet Thursday to discuss Q2 planning?",
        body="""\
Hi,

I'd like to schedule a meeting this Thursday at 2pm to go over our Q2
roadmap. Could you confirm your availability and prepare a brief status
update on the current sprint?

We need to finalize priorities before the board meeting next Monday.

Thanks,
Sarah""",
        labels=["INBOX", "UNREAD", "IMPORTANT"],
        expect_tasks=True,
        min_tasks=1,
        expected_email_type=EmailType.PERSONAL,
    ),
    EmailSpecimen(
        name="code_review_request",
        category="actionable",
        sender="Dave Kumar",
        sender_email="dave.kumar@company.com",
        subject="PR #142: Please review auth refactor",
        body="""\
Hey,

I've opened PR #142 with the auth module refactor we discussed. It's about
400 lines of changes.

Could you review it by end of day Wednesday? I'd like to merge before the
release freeze on Thursday.

Key changes:
- Moved to JWT-based tokens
- Added refresh token rotation
- Updated all integration tests

Link: https://github.com/company/app/pull/142

Thanks!
Dave""",
        labels=["INBOX", "UNREAD"],
        expect_tasks=True,
        min_tasks=1,
        expected_email_type=EmailType.PERSONAL,
    ),
    EmailSpecimen(
        name="deadline_reminder_from_category_updates",
        category="actionable",
        sender="Finance Team",
        sender_email="finance@company.com",
        subject="URGENT: Expense reports due by Friday",
        body="""\
Hi,

This is a reminder that all expense reports for January must be submitted
by this Friday, January 19th.

Please log into the expense system and submit any outstanding reports.
Late submissions will not be processed until next month.

If you have questions, please contact the finance team.

Regards,
Finance Team""",
        labels=["INBOX", "UNREAD", "CATEGORY_UPDATES"],
        expect_tasks=True,
        min_tasks=1,
        expected_email_type=EmailType.PERSONAL,
    ),
]


def _make_email(specimen: EmailSpecimen) -> Email:
    """Convert an EmailSpecimen into an Email object for analysis."""
    return Email(
        id=f"test-{specimen.name}",
        thread_id=f"thread-{specimen.name}",
        subject=specimen.subject,
        sender=specimen.sender,
        sender_email=specimen.sender_email,
        recipient="me@example.com",
        date=datetime(2024, 1, 15, 10, 0),
        body=specimen.body,
        labels=specimen.labels,
    )


_NO_TASK_SPECIMENS = [s for s in SPECIMENS if not s.expect_tasks]
_ACTIONABLE_SPECIMENS = [s for s in SPECIMENS if s.expect_tasks]


@pytest.mark.integration
class TestEmailClassification:
    """Integration tests verifying the LLM correctly classifies email types.

    Uses the real OpenAI API to validate that prompt instructions correctly
    cause the LLM to skip marketing/promotional/automated emails while still
    extracting tasks from actionable ones.
    """

    @pytest.fixture
    def analyzer(self):
        """Create an EmailAnalyzer with real OpenAI connection."""
        return EmailAnalyzer()

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    @pytest.mark.parametrize(
        "specimen",
        _NO_TASK_SPECIMENS,
        ids=[s.name for s in _NO_TASK_SPECIMENS],
    )
    def test_no_tasks_extracted(self, analyzer, specimen):
        """Non-actionable emails should produce zero tasks."""
        email = _make_email(specimen)
        result = analyzer.analyze(email)

        assert len(result.tasks) == 0, (
            f"Expected 0 tasks for {specimen.category} email '{specimen.name}', "
            f"but got {len(result.tasks)}: {[t.title for t in result.tasks]}"
        )
        assert result.requires_response is False
        if specimen.expected_email_type is not None:
            assert result.email_type == specimen.expected_email_type, (
                f"Expected email_type={specimen.expected_email_type.value} "
                f"for '{specimen.name}', but got {result.email_type.value}"
            )

        print(f"\n  [{specimen.category}] {specimen.name}: "
              f"type={result.email_type.value}, 0 tasks -- PASS")

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    )
    @pytest.mark.parametrize(
        "specimen",
        _ACTIONABLE_SPECIMENS,
        ids=[s.name for s in _ACTIONABLE_SPECIMENS],
    )
    def test_tasks_extracted(self, analyzer, specimen):
        """Actionable emails should produce at least the minimum expected tasks."""
        email = _make_email(specimen)
        result = analyzer.analyze(email)

        assert len(result.tasks) >= specimen.min_tasks, (
            f"Expected >= {specimen.min_tasks} tasks for '{specimen.name}', "
            f"but got {len(result.tasks)}"
        )
        assert result.is_actionable is True, (
            f"Expected is_actionable=True for '{specimen.name}', "
            f"but got is_actionable={result.is_actionable} (type={result.email_type.value})"
        )
        if specimen.expected_email_type is not None:
            assert result.email_type == specimen.expected_email_type, (
                f"Expected email_type={specimen.expected_email_type.value} "
                f"for '{specimen.name}', but got {result.email_type.value}"
            )

        print(f"\n  [{specimen.category}] {specimen.name}: "
              f"type={result.email_type.value}, {len(result.tasks)} tasks -- PASS")
        for i, task in enumerate(result.tasks, 1):
            print(f"    {i}. {task.title} (priority={task.priority.value})")
