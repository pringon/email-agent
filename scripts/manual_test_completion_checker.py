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
    5. Cleans up the test task
"""

import sys
from pathlib import Path

# Add project root to sys.path so `src` is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta

from src.completion import CompletionChecker
from src.tasks import TaskManager
from src.tasks.models import Task, TaskStatus


def main() -> None:
    task_manager = TaskManager()
    checker = CompletionChecker(task_manager=task_manager)

    # --- Step 1: Fetch recent sent emails ---
    print("Step 1: Fetching recent sent emails ...")
    since = datetime.now() - timedelta(hours=48)
    sent_emails = list(checker.fetch_sent_emails(since=since, max_results=5))

    if not sent_emails:
        print("  No sent emails found in the last 48 hours.")
        print("  Send an email reply first, then re-run this test.")
        sys.exit(1)

    print(f"  Found {len(sent_emails)} sent email(s):")
    for i, email in enumerate(sent_emails):
        print(f"    [{i}] To: {email.recipient}  Subject: {email.subject}")
        print(f"        Thread ID: {email.thread_id}  Date: {email.date}")

    # Use the first sent email's thread ID
    target_email = sent_emails[0]
    thread_id = target_email.thread_id
    print(f"\n  Using thread ID: {thread_id}")

    # --- Step 2: Create a task linked to this thread ---
    print("\nStep 2: Creating a test task linked to the thread ...")
    test_task = Task(
        title="[SMOKE TEST] Auto-complete via CompletionChecker",
        notes="Created by manual_test_completion_checker.py",
        source_thread_id=thread_id,
        source_email_id=f"smoke-test-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        status=TaskStatus.NEEDS_ACTION,
    )
    created_task = task_manager.create_task(test_task)
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

    # --- Step 5: Clean up ---
    print("\nStep 5: Cleaning up test task ...")
    task_manager.delete_task(created_task.id)
    print("  Test task deleted.")

    # --- Summary ---
    print("\n" + "=" * 50)
    if updated_task.status == TaskStatus.COMPLETED and not result.errors:
        print("  SMOKE TEST PASSED")
    else:
        print("  SMOKE TEST FAILED")
        if result.errors:
            for err in result.errors:
                print(f"    Error: {err}")
    print("=" * 50)


if __name__ == "__main__":
    main()
