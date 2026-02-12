"""End-to-end test for CompletionChecker.

Tests the full flow: fetch sent emails from Gmail, match against tasks in
Google Tasks, and auto-complete matching tasks.

Run locally:
    python -m pytest tests/test_completion_e2e.py -v -s

Configure via environment variables:
    GMAIL_CREDENTIALS_PATH  - Path to OAuth credentials.json
    GMAIL_TOKEN_PATH        - Path to OAuth token.json
    GMAIL_NON_INTERACTIVE   - Set to "1" to fail fast if re-auth needed
    TASKS_CREDENTIALS_PATH  - Path to OAuth credentials.json for Tasks
    TASKS_TOKEN_PATH        - Path to OAuth tasks_token.json
    TASKS_NON_INTERACTIVE   - Set to "1" to fail fast if re-auth needed
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.completion import CompletionChecker
from src.completion.reply_resolver import ReplyResolver
from src.tasks import TaskManager
from src.tasks.models import TaskStatus

from tests.completion_test_helpers import (
    create_test_task,
    fetch_thread_id_from_sent_mail,
    wait_for_task_in_list,
)


@pytest.mark.integration
class TestCompletionCheckerE2E:
    """E2E tests for CompletionChecker with real Gmail and Tasks APIs."""

    @pytest.fixture(scope="class")
    def task_manager(self):
        """Create a TaskManager with real credentials."""
        return TaskManager()

    @pytest.fixture(scope="class")
    def checker(self, task_manager):
        """Create a CompletionChecker with real Gmail/Tasks APIs.

        Uses a mock ReplyResolver that resolves all tasks for a matched
        thread. The e2e tests verify plumbing (thread matching, task
        discovery, completion) — LLM judgment is tested separately in
        the ReplyResolver unit tests.
        """
        mock_resolver = MagicMock(spec=ReplyResolver)
        mock_resolver.resolve.side_effect = (
            lambda reply_body, subject, tasks: [t.id for t in tasks if t.id]
        )
        return CompletionChecker(
            task_manager=task_manager,
            reply_resolver=mock_resolver,
        )

    def test_fetch_sent_emails(self, checker):
        """Verify we can fetch sent emails from Gmail."""
        since = datetime.now() - timedelta(days=7)
        sent_emails = list(checker.fetch_sent_emails(since=since, max_results=5))

        assert len(sent_emails) > 0, (
            "No sent emails found in the last 7 days. "
            "The test Gmail account needs at least one sent message."
        )

        # Verify sent email fields are populated
        email = sent_emails[0]
        assert email.id, "Sent email should have an ID"
        assert email.thread_id, "Sent email should have a thread ID"
        assert email.date, "Sent email should have a date"

        print(f"\nFetched {len(sent_emails)} sent email(s)")
        print(f"  First email thread_id: {email.thread_id}")
        print(f"  Subject: {email.subject[:50]}...")

    def test_completion_check_runs_without_errors(self, checker):
        """CompletionChecker completes without errors against real APIs.

        Verifies the full check_for_completions flow works end-to-end.
        The number of completions depends on account state (existing tasks
        and sent emails), so we only assert error-free execution and
        result consistency.
        """
        since = datetime.now() - timedelta(days=7)
        result = checker.check_for_completions(since=since, max_results=5)

        assert result.errors == [], f"Unexpected errors: {result.errors}"
        assert result.total_completed >= 0
        assert result.threads_matched >= 0
        assert result.total_completed == len(result.tasks_completed)

        print(f"\nSent emails scanned: {result.sent_emails_scanned}")
        print(f"Threads matched: {result.threads_matched}")
        print(f"Tasks completed: {result.total_completed}")

    def test_auto_complete_task_for_replied_thread(self, checker, task_manager):
        """Full e2e: create a task linked to a sent email thread, then verify
        CompletionChecker auto-completes it.

        Steps:
            1. Fetch a recent sent email to get a real thread_id
            2. Create a test task linked to that thread_id
            3. Run CompletionChecker
            4. Verify the task was marked as completed
            5. Clean up
        """
        # Steps 1-2: Get a thread_id and create a linked test task
        thread_id, since = fetch_thread_id_from_sent_mail(checker)
        created_task = create_test_task(
            task_manager, thread_id,
            prefix="E2E TEST",
            creator="test_completion_e2e.py",
        )
        print(f"\nUsing thread_id from sent email: {thread_id}")
        print(f"Created test task: {created_task.id}")

        try:
            # Verify task was created with correct metadata
            fetched = task_manager.get_task(
                created_task.id, list_id=created_task.task_list_id
            )
            assert fetched.source_thread_id == thread_id, (
                f"Task thread_id mismatch: {fetched.source_thread_id} != {thread_id}"
            )
            assert fetched.status == TaskStatus.NEEDS_ACTION

            # Wait for the task to be visible in list_tasks (API propagation)
            wait_for_task_in_list(task_manager, thread_id)

            # Step 3: Run CompletionChecker
            result = checker.check_for_completions(since=since, max_results=10)

            print(f"Scanned {result.sent_emails_scanned} sent emails")
            print(f"Threads matched: {result.threads_matched}")
            print(f"Tasks completed: {result.total_completed}")
            if result.errors:
                print(f"Errors: {result.errors}")

            # Step 4: Verify the task was completed
            assert result.errors == [], f"Errors during completion check: {result.errors}"
            assert result.total_completed >= 1, (
                f"Expected at least 1 task completed, got {result.total_completed}"
            )
            assert created_task.id in result.tasks_completed, (
                f"Test task {created_task.id} not in completed list: {result.tasks_completed}"
            )

            # Double-check by fetching the task directly
            completed_task = task_manager.get_task(
                created_task.id, list_id=created_task.task_list_id
            )
            assert completed_task.status == TaskStatus.COMPLETED, (
                f"Task status should be COMPLETED, got {completed_task.status}"
            )

            print("Task was auto-completed successfully!")

        finally:
            # Step 5: Clean up - delete the test task
            try:
                task_manager.delete_task(
                    created_task.id, list_id=created_task.task_list_id
                )
                print(f"Cleaned up test task: {created_task.id}")
            except Exception as e:
                print(f"Warning: Failed to clean up test task {created_task.id}: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
