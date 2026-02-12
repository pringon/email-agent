"""Shared helpers for completion checker tests and manual smoke tests.

Used by:
    - tests/test_completion_e2e.py (pytest e2e test)
    - scripts/manual_test_completion_checker.py (manual smoke test)
"""

import time
from datetime import datetime, timedelta
from typing import Optional

from src.completion import CompletionChecker
from src.tasks import TaskManager
from src.tasks.models import Task, TaskStatus


def fetch_thread_id_from_sent_mail(
    checker: CompletionChecker,
    since: Optional[datetime] = None,
    max_results: int = 5,
) -> tuple[str, datetime]:
    """Fetch recent sent emails and return a thread_id for testing.

    Args:
        checker: CompletionChecker instance.
        since: How far back to look. Defaults to 7 days.
        max_results: Max emails to fetch.

    Returns:
        Tuple of (thread_id, since_datetime). The since value is returned
        so callers can reuse the same window for check_for_completions().

    Raises:
        RuntimeError: If no sent emails found.
    """
    if since is None:
        since = datetime.now() - timedelta(days=7)

    sent_emails = list(checker.fetch_sent_emails(since=since, max_results=max_results))

    if not sent_emails:
        raise RuntimeError(
            f"No sent emails found since {since}. "
            "Send an email reply first, then re-run."
        )

    return sent_emails[0].thread_id, since


def create_test_task(
    task_manager: TaskManager,
    thread_id: str,
    prefix: str = "TEST",
    creator: str = "test helper",
) -> Task:
    """Create a test task linked to a Gmail thread.

    Args:
        task_manager: TaskManager instance.
        thread_id: Gmail thread ID to link the task to.
        prefix: Prefix for the task title (e.g., "SMOKE TEST", "E2E TEST").
        creator: Description of who created this task (for the notes field).

    Returns:
        Created Task with ID populated.
    """
    test_task = Task(
        title=f"[{prefix}] Auto-complete via CompletionChecker",
        notes=f"Created by {creator}",
        source_thread_id=thread_id,
        source_email_id=f"{prefix.lower().replace(' ', '-')}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        status=TaskStatus.NEEDS_ACTION,
    )
    return task_manager.create_task(test_task)


def wait_for_task_in_list(
    task_manager: TaskManager,
    thread_id: str,
    timeout: float = 10,
    interval: float = 1,
) -> None:
    """Poll list_tasks until a task with the given thread_id is visible.

    The Google Tasks API can have eventual consistency delays between
    creating a task and it appearing in list queries.

    Args:
        task_manager: TaskManager instance.
        thread_id: Gmail thread ID to wait for.
        timeout: Maximum seconds to wait.
        interval: Seconds between polls.

    Raises:
        TimeoutError: If the task doesn't appear within the timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for task in task_manager.list_tasks(show_completed=False):
            if task.source_thread_id == thread_id:
                return
        time.sleep(interval)
    raise TimeoutError(
        f"Task with thread_id {thread_id} not visible in list_tasks "
        f"after {timeout}s"
    )
