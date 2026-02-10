#!/usr/bin/env python3
"""Manual smoke test: verify CompletionChecker detects sent replies and completes tasks.

Run from project root:
    python scripts/manual_test_completion_checker.py

Requires:
    - config/credentials.json (OAuth client credentials)
    - config/token.json (Gmail OAuth token)
    - config/tasks_token.json (Tasks OAuth token)

What this test does:
    1. Fetches recent sent emails to find a real thread ID
    2. Creates a task linked to that thread in Google Tasks
    3. Runs CompletionChecker.check_for_completions() to detect the match
    4. Verifies the task was auto-completed

Note: The test task is NOT deleted after the test, so you can verify
it exists in Google Tasks. Look for tasks prefixed with [SMOKE TEST].
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to sys.path so `src` and `tests` are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.completion_test_helpers import create_test_task, fetch_thread_id_from_sent_mail
from src.completion import CompletionChecker
from src.tasks import TaskManager
from src.tasks.models import TaskStatus


def main() -> None:
    task_manager = TaskManager()
    checker = CompletionChecker(task_manager=task_manager)

    # --- Step 1: Fetch recent sent emails ---
    print("Step 1: Fetching recent sent emails ...")
    try:
        thread_id, since = fetch_thread_id_from_sent_mail(
            checker, since=datetime.now() - timedelta(hours=48)
        )
    except RuntimeError as e:
        print(f"  {e}")
        sys.exit(1)
    print(f"  Using thread ID: {thread_id}")

    # --- Step 2: Create a task linked to this thread ---
    print("\nStep 2: Creating a test task linked to the thread ...")
    created_task = create_test_task(
        task_manager, thread_id,
        prefix="SMOKE TEST",
        creator="manual_test_completion_checker.py",
    )
    print(f"  Created task: {created_task.id}")
    print(f"  Title: {created_task.title}")
    print(f"  Status: {created_task.status.value}")
    print(f"  Thread ID: {created_task.source_thread_id}")

    # --- Step 3: Run CompletionChecker ---
    print("\nStep 3: Running CompletionChecker.check_for_completions() ...")
    result = checker.check_for_completions(since=since)

    print(f"  Sent emails scanned: {result.sent_emails_scanned}")
    print(f"  Threads matched: {result.threads_matched}")
    print(f"  Tasks completed: {result.total_completed}")
    if result.errors:
        print(f"  Errors: {result.errors}")
    if result.thread_task_map:
        for tid, task_ids in result.thread_task_map.items():
            print(f"  Thread {tid} -> tasks: {task_ids}")

    # --- Step 4: Verify the task was completed ---
    print("\nStep 4: Verifying task status ...")
    updated_task = task_manager.get_task(created_task.id)
    print(f"  Task status: {updated_task.status.value}")

    if updated_task.status == TaskStatus.COMPLETED:
        print("  PASS: Task was auto-completed by CompletionChecker!")
    else:
        print("  FAIL: Task was NOT completed. Check the output above for errors.")

    # --- Summary ---
    print("\n" + "=" * 50)
    if updated_task.status == TaskStatus.COMPLETED and not result.errors:
        print("  SMOKE TEST PASSED")
        print(f"\n  Task left in Google Tasks for verification:")
        print(f"    ID: {created_task.id}")
        print(f"    Title: {created_task.title}")
    else:
        print("  SMOKE TEST FAILED")
        if result.errors:
            for err in result.errors:
                print(f"    Error: {err}")
    print("=" * 50)


if __name__ == "__main__":
    main()
