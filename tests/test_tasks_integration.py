"""
Integration test for Google Tasks API authentication and basic operations.

Run with: python -m pytest tests/test_tasks_integration.py -v

Configure via environment variables:
    TASKS_CREDENTIALS_PATH  - Path to OAuth credentials.json
    TASKS_TOKEN_PATH        - Path to OAuth tasks_token.json
    TASKS_NON_INTERACTIVE   - Set to "1" to fail fast if re-auth needed

Note: First run requires interactive OAuth consent to generate tasks_token.json.
"""

from pathlib import Path

import pytest

from src.tasks import TasksAuthenticator

# Paths (for test_credentials_file_exists only)
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CREDENTIALS_PATH = PROJECT_ROOT / "config" / "credentials.json"


@pytest.mark.integration
class TestTasksIntegration:
    """Integration tests for Google Tasks API."""

    @pytest.fixture(scope="class")
    def tasks_service(self):
        """Create Tasks service using TasksAuthenticator."""
        auth = TasksAuthenticator()
        return auth.get_service()

    def test_credentials_file_exists(self):
        """Verify credentials.json exists at the default location."""
        assert DEFAULT_CREDENTIALS_PATH.exists(), (
            f"credentials.json not found at {DEFAULT_CREDENTIALS_PATH}"
        )

    def test_can_authenticate(self, tasks_service):
        """Verify we can authenticate with Tasks API."""
        assert tasks_service is not None

    def test_can_list_task_lists(self, tasks_service):
        """Fetch task lists and verify we can list them."""
        results = tasks_service.tasklists().list(maxResults=10).execute()
        task_lists = results.get("items", [])
        
        assert len(task_lists) > 0, "No task lists found"
        
        print(f"\nFound {len(task_lists)} task list(s):")
        for tl in task_lists:
            print(f"  - {tl['title']} (id: {tl['id']})")

    def test_can_create_and_delete_task(self, tasks_service):
        """Create a test task and then delete it."""
        # Get the default task list
        task_lists = tasks_service.tasklists().list(maxResults=1).execute()
        default_list_id = task_lists["items"][0]["id"]

        # Create a test task
        test_task = {
            "title": "[TEST] Integration test task - safe to delete",
            "notes": "Created by test_tasks_integration.py",
        }
        created = tasks_service.tasks().insert(
            tasklist=default_list_id,
            body=test_task,
        ).execute()

        print(f"\nCreated task: {created['title']} (id: {created['id']})")

        assert created["id"] is not None
        assert created["title"] == test_task["title"]

        # Clean up: delete the task
        tasks_service.tasks().delete(
            tasklist=default_list_id,
            task=created["id"],
        ).execute()

        print(f"Deleted task: {created['id']}")

    def test_can_read_task_details(self, tasks_service):
        """Create a task, read it back, then delete it."""
        # Get the default task list
        task_lists = tasks_service.tasklists().list(maxResults=1).execute()
        default_list_id = task_lists["items"][0]["id"]

        # Create a test task with notes
        test_task = {
            "title": "[TEST] Read test task",
            "notes": "thread_id:abc123\nemail_id:xyz789",
        }
        created = tasks_service.tasks().insert(
            tasklist=default_list_id,
            body=test_task,
        ).execute()

        try:
            # Read the task back
            fetched = tasks_service.tasks().get(
                tasklist=default_list_id,
                task=created["id"],
            ).execute()

            assert fetched["id"] == created["id"]
            assert fetched["title"] == test_task["title"]
            assert fetched["notes"] == test_task["notes"]

            print(f"\nTask notes preserved: {fetched['notes']}")

        finally:
            # Clean up
            tasks_service.tasks().delete(
                tasklist=default_list_id,
                task=created["id"],
            ).execute()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
