"""Unit tests for the ReplyResolver module."""

import json
from unittest.mock import MagicMock

import pytest

from src.analyzer.adapter import LLMAdapter
from src.analyzer.exceptions import LLMResponseError
from src.completion.reply_resolver import ReplyResolver
from src.tasks.models import Task


# ==================== Fixtures ====================


@pytest.fixture
def mock_adapter():
    """Create a mock LLMAdapter."""
    adapter = MagicMock(spec=LLMAdapter)
    adapter.model_name = "test-model"
    adapter.provider_name = "test-provider"
    return adapter


@pytest.fixture
def sample_tasks():
    """Create sample tasks for testing."""
    return [
        Task(
            title="Review proposal",
            id="task1",
            notes="Priority: high\nConfidence: 95%\n\nReview the Q1 proposal document",
        ),
        Task(
            title="Schedule meeting with Sarah",
            id="task2",
            notes="Priority: medium\n\nSet up a 30-min sync about the project timeline",
        ),
        Task(
            title="Update budget spreadsheet",
            id="task3",
            notes="Priority: low\n\nAdd Q2 projections to the budget sheet",
        ),
    ]


@pytest.fixture
def resolver(mock_adapter):
    """Create a ReplyResolver with mock adapter."""
    return ReplyResolver(adapter=mock_adapter)


def _make_response(resolved_tasks: list[dict]) -> str:
    """Helper to create a valid JSON response string."""
    return json.dumps({"resolved_tasks": resolved_tasks})


# ==================== Core Resolution Tests ====================


class TestResolve:
    """Tests for the resolve method."""

    def test_resolve_all_tasks(self, resolver, mock_adapter, sample_tasks):
        """Test when reply addresses all tasks."""
        mock_adapter.complete.return_value = _make_response(
            [
                {"task_id": "task1", "resolved": True, "reason": "Reviewed proposal"},
                {"task_id": "task2", "resolved": True, "reason": "Meeting scheduled"},
                {"task_id": "task3", "resolved": True, "reason": "Budget updated"},
            ]
        )

        result = resolver.resolve("I've handled everything.", "Re: Tasks", sample_tasks)

        assert sorted(result) == ["task1", "task2", "task3"]

    def test_resolve_some_tasks(self, resolver, mock_adapter, sample_tasks):
        """Test when reply addresses only some tasks."""
        mock_adapter.complete.return_value = _make_response(
            [
                {"task_id": "task1", "resolved": True, "reason": "Proposal reviewed"},
                {"task_id": "task2", "resolved": False, "reason": "Not mentioned"},
                {"task_id": "task3", "resolved": True, "reason": "Budget updated"},
            ]
        )

        result = resolver.resolve(
            "I reviewed the proposal and updated the budget.", "Re: Tasks", sample_tasks
        )

        assert sorted(result) == ["task1", "task3"]

    def test_resolve_no_tasks(self, resolver, mock_adapter, sample_tasks):
        """Test when reply doesn't address any tasks."""
        mock_adapter.complete.return_value = _make_response(
            [
                {"task_id": "task1", "resolved": False, "reason": "Not addressed"},
                {"task_id": "task2", "resolved": False, "reason": "Not addressed"},
                {"task_id": "task3", "resolved": False, "reason": "Not addressed"},
            ]
        )

        result = resolver.resolve("Thanks for the update.", "Re: FYI", sample_tasks)

        assert result == []

    def test_resolve_single_task(self, resolver, mock_adapter):
        """Test with a single task in the thread."""
        tasks = [Task(title="Reply to invoice", id="t1")]
        mock_adapter.complete.return_value = _make_response(
            [{"task_id": "t1", "resolved": True, "reason": "Invoice addressed"}]
        )

        result = resolver.resolve("Here's the payment.", "Re: Invoice", tasks)

        assert result == ["t1"]

    def test_resolve_empty_task_list(self, resolver, mock_adapter):
        """Test with empty task list returns empty without LLM call."""
        result = resolver.resolve("Some reply", "Subject", [])

        assert result == []
        mock_adapter.complete.assert_not_called()

    def test_resolve_filters_unknown_task_ids(self, resolver, mock_adapter, sample_tasks):
        """Test that task IDs not in the input list are filtered out."""
        mock_adapter.complete.return_value = _make_response(
            [
                {"task_id": "task1", "resolved": True, "reason": "Addressed"},
                {"task_id": "unknown_id", "resolved": True, "reason": "Hallucinated"},
                {"task_id": "task2", "resolved": False, "reason": "Not addressed"},
            ]
        )

        result = resolver.resolve("Reply text", "Re: Subject", sample_tasks)

        assert result == ["task1"]

    def test_resolve_uses_json_mode(self, resolver, mock_adapter, sample_tasks):
        """Test that the adapter is called with json_mode=True."""
        mock_adapter.complete.return_value = _make_response(
            [{"task_id": "task1", "resolved": True, "reason": "Done"}]
        )

        resolver.resolve("Reply", "Subject", sample_tasks)

        call_kwargs = mock_adapter.complete.call_args.kwargs
        assert call_kwargs.get("json_mode") is True

    def test_resolve_uses_zero_temperature(self, resolver, mock_adapter, sample_tasks):
        """Test that the adapter is called with temperature=0.0."""
        mock_adapter.complete.return_value = _make_response(
            [{"task_id": "task1", "resolved": True, "reason": "Done"}]
        )

        resolver.resolve("Reply", "Subject", sample_tasks)

        call_kwargs = mock_adapter.complete.call_args.kwargs
        assert call_kwargs.get("temperature") == 0.0


# ==================== Prompt Construction Tests ====================


class TestBuildMessages:
    """Tests for message construction."""

    def test_includes_task_titles_in_prompt(self, resolver, mock_adapter, sample_tasks):
        """Test that task titles appear in the LLM prompt."""
        mock_adapter.complete.return_value = _make_response([])

        resolver.resolve("Reply text", "Subject", sample_tasks)

        call_args = mock_adapter.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_content = messages[1].content

        assert "Review proposal" in user_content
        assert "Schedule meeting with Sarah" in user_content
        assert "Update budget spreadsheet" in user_content

    def test_includes_task_ids_in_prompt(self, resolver, mock_adapter, sample_tasks):
        """Test that task IDs appear in the LLM prompt."""
        mock_adapter.complete.return_value = _make_response([])

        resolver.resolve("Reply text", "Subject", sample_tasks)

        call_args = mock_adapter.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_content = messages[1].content

        assert "task1" in user_content
        assert "task2" in user_content
        assert "task3" in user_content

    def test_includes_subject_in_prompt(self, resolver, mock_adapter, sample_tasks):
        """Test that the email subject appears in the prompt."""
        mock_adapter.complete.return_value = _make_response([])

        resolver.resolve("Reply text", "Re: Important Meeting", sample_tasks)

        call_args = mock_adapter.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_content = messages[1].content

        assert "Re: Important Meeting" in user_content

    def test_includes_reply_body_in_prompt(self, resolver, mock_adapter, sample_tasks):
        """Test that the reply body appears in the prompt."""
        mock_adapter.complete.return_value = _make_response([])
        reply = "I've reviewed the proposal and it looks good."

        resolver.resolve(reply, "Subject", sample_tasks)

        call_args = mock_adapter.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_content = messages[1].content

        assert reply in user_content

    def test_truncates_long_reply(self, resolver, mock_adapter, sample_tasks):
        """Test that long reply bodies are truncated."""
        mock_adapter.complete.return_value = _make_response([])
        long_reply = "A" * 10000

        resolver.resolve(long_reply, "Subject", sample_tasks)

        call_args = mock_adapter.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_content = messages[1].content

        # Should be truncated to MAX_REPLY_LENGTH
        assert "A" * 10000 not in user_content
        assert "A" * 8000 in user_content

    def test_strips_metadata_from_task_notes(self, resolver, mock_adapter):
        """Test that email-agent metadata is stripped from task notes in prompt."""
        tasks = [
            Task(
                title="Review doc",
                id="t1",
                notes="Review the doc carefully\n\n---email-agent-metadata---\nemail_id:msg1\nthread_id:thread1",
            )
        ]
        mock_adapter.complete.return_value = _make_response([])

        resolver.resolve("Reply", "Subject", tasks)

        call_args = mock_adapter.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_content = messages[1].content

        assert "Review the doc carefully" in user_content
        assert "email-agent-metadata" not in user_content

    def test_task_without_notes(self, resolver, mock_adapter):
        """Test tasks with no notes still work."""
        tasks = [Task(title="Do something", id="t1", notes=None)]
        mock_adapter.complete.return_value = _make_response([])

        resolver.resolve("Reply", "Subject", tasks)

        call_args = mock_adapter.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_content = messages[1].content

        assert "Do something" in user_content

    def test_has_system_and_user_messages(self, resolver, mock_adapter, sample_tasks):
        """Test that both system and user messages are built."""
        mock_adapter.complete.return_value = _make_response([])

        resolver.resolve("Reply", "Subject", sample_tasks)

        call_args = mock_adapter.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]

        assert len(messages) == 2
        assert messages[0].role.value == "system"
        assert messages[1].role.value == "user"


# ==================== Response Parsing Tests ====================


class TestParseResponse:
    """Tests for response parsing."""

    def test_parse_valid_response(self, resolver, sample_tasks):
        """Test parsing a valid JSON response."""
        response = _make_response(
            [
                {"task_id": "task1", "resolved": True, "reason": "Done"},
                {"task_id": "task2", "resolved": False, "reason": "Not done"},
            ]
        )

        result = resolver._parse_response(response, sample_tasks)

        assert result == ["task1"]

    def test_parse_invalid_json_raises(self, resolver, sample_tasks):
        """Test that invalid JSON raises LLMResponseError."""
        with pytest.raises(LLMResponseError) as exc_info:
            resolver._parse_response("not valid json", sample_tasks)

        assert exc_info.value.raw_response == "not valid json"

    def test_parse_missing_resolved_tasks_key(self, resolver, sample_tasks):
        """Test response with missing resolved_tasks key."""
        response = json.dumps({"other_key": "value"})

        result = resolver._parse_response(response, sample_tasks)

        assert result == []

    def test_parse_empty_resolved_tasks(self, resolver, sample_tasks):
        """Test response with empty resolved_tasks array."""
        response = _make_response([])

        result = resolver._parse_response(response, sample_tasks)

        assert result == []

    def test_parse_skips_malformed_entries(self, resolver, sample_tasks):
        """Test that malformed entries are skipped."""
        response = json.dumps(
            {
                "resolved_tasks": [
                    {"task_id": "task1", "resolved": True, "reason": "Good"},
                    {"missing_fields": True},  # Malformed
                    {"task_id": "task2", "resolved": True, "reason": "Good"},
                ]
            }
        )

        result = resolver._parse_response(response, sample_tasks)

        assert sorted(result) == ["task1", "task2"]

    def test_parse_filters_invalid_task_ids(self, resolver, sample_tasks):
        """Test that task IDs not in input are filtered."""
        response = _make_response(
            [
                {"task_id": "task1", "resolved": True, "reason": "Good"},
                {"task_id": "fake_id", "resolved": True, "reason": "Hallucinated"},
            ]
        )

        result = resolver._parse_response(response, sample_tasks)

        assert result == ["task1"]


# ==================== Retry Logic Tests ====================


class TestRetryLogic:
    """Tests for retry behavior on parse errors."""

    def test_retry_on_parse_error(self, mock_adapter, sample_tasks):
        """Test that a failed parse is retried."""
        mock_adapter.complete.side_effect = [
            "not json",  # First call: bad JSON
            _make_response(  # Second call: valid JSON
                [{"task_id": "task1", "resolved": True, "reason": "OK"}]
            ),
        ]

        resolver = ReplyResolver(adapter=mock_adapter, max_retries=2)
        result = resolver.resolve("Reply", "Subject", sample_tasks)

        assert result == ["task1"]
        assert mock_adapter.complete.call_count == 2

    def test_max_retries_exceeded(self, mock_adapter, sample_tasks):
        """Test that LLMResponseError is raised after max retries."""
        mock_adapter.complete.return_value = "always bad json"

        resolver = ReplyResolver(adapter=mock_adapter, max_retries=1)

        with pytest.raises(LLMResponseError):
            resolver.resolve("Reply", "Subject", sample_tasks)

        # 1 initial + 1 retry = 2 calls
        assert mock_adapter.complete.call_count == 2


# ==================== Custom Prompts Tests ====================


class TestCustomPrompts:
    """Tests for custom prompt support."""

    def test_custom_system_prompt(self, mock_adapter, sample_tasks):
        """Test using a custom system prompt."""
        mock_adapter.complete.return_value = _make_response([])
        resolver = ReplyResolver(
            adapter=mock_adapter, system_prompt="Custom system prompt"
        )

        resolver.resolve("Reply", "Subject", sample_tasks)

        messages = mock_adapter.complete.call_args.kwargs["messages"]
        assert messages[0].content == "Custom system prompt"

    def test_custom_user_prompt_template(self, mock_adapter, sample_tasks):
        """Test using a custom user prompt template."""
        mock_adapter.complete.return_value = _make_response([])
        template = "Reply: {reply_body}\nSubject: {subject}\nTasks: {tasks_list}"
        resolver = ReplyResolver(
            adapter=mock_adapter, user_prompt_template=template
        )

        resolver.resolve("Test reply", "Test subject", sample_tasks)

        messages = mock_adapter.complete.call_args.kwargs["messages"]
        assert "Reply: Test reply" in messages[1].content
        assert "Subject: Test subject" in messages[1].content


# ==================== Format Tasks List Tests ====================


class TestFormatTasksList:
    """Tests for the task formatting helper."""

    def test_format_includes_id_and_title(self, resolver):
        """Test that formatted list includes task ID and title."""
        tasks = [Task(title="Do thing", id="t1")]

        result = resolver._format_tasks_list(tasks)

        assert "Task ID: t1" in result
        assert "Title: Do thing" in result

    def test_format_includes_description(self, resolver):
        """Test that formatted list includes notes excerpt."""
        tasks = [Task(title="Task", id="t1", notes="Some important context")]

        result = resolver._format_tasks_list(tasks)

        assert "Description: Some important context" in result

    def test_format_truncates_long_notes(self, resolver):
        """Test that long notes are truncated in the formatted list."""
        long_notes = "A" * 300
        tasks = [Task(title="Task", id="t1", notes=long_notes)]

        result = resolver._format_tasks_list(tasks)

        assert "..." in result
        assert "A" * 300 not in result

    def test_format_strips_metadata(self, resolver):
        """Test that metadata is stripped from notes in formatted list."""
        tasks = [
            Task(
                title="Task",
                id="t1",
                notes="User notes\n\n---email-agent-metadata---\nemail_id:msg1",
            )
        ]

        result = resolver._format_tasks_list(tasks)

        assert "User notes" in result
        assert "email-agent-metadata" not in result
