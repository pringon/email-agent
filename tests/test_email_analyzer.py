"""Unit tests for the EmailAnalyzer module."""

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.analyzer import (
    AnalysisResult,
    EmailAnalyzer,
    ExtractedTask,
    LLMAdapter,
    LLMAuthenticationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    Message,
    MessageRole,
    OpenAIAdapter,
    Priority,
)
from src.fetcher import Email


class TestPriority:
    """Tests for Priority enum."""

    def test_priority_values(self):
        """Test priority enum values."""
        assert Priority.LOW.value == "low"
        assert Priority.MEDIUM.value == "medium"
        assert Priority.HIGH.value == "high"
        assert Priority.URGENT.value == "urgent"

    def test_priority_from_string(self):
        """Test creating priority from string."""
        assert Priority("low") == Priority.LOW
        assert Priority("urgent") == Priority.URGENT


class TestMessage:
    """Tests for Message dataclass."""

    def test_to_dict(self):
        """Test message serialization."""
        msg = Message(role=MessageRole.SYSTEM, content="You are helpful.")
        data = msg.to_dict()
        assert data == {"role": "system", "content": "You are helpful."}

    def test_user_message(self):
        """Test user message serialization."""
        msg = Message(role=MessageRole.USER, content="Hello!")
        data = msg.to_dict()
        assert data["role"] == "user"

    def test_assistant_message(self):
        """Test assistant message serialization."""
        msg = Message(role=MessageRole.ASSISTANT, content="Hi there!")
        data = msg.to_dict()
        assert data["role"] == "assistant"


class TestExtractedTask:
    """Tests for ExtractedTask dataclass."""

    def test_to_dict(self):
        """Test task serialization."""
        task = ExtractedTask(
            title="Review proposal",
            description="Review the Q1 proposal document",
            priority=Priority.HIGH,
            source_email_id="msg123",
            source_thread_id="thread456",
            due_date=date(2024, 1, 20),
            confidence=0.95,
        )

        data = task.to_dict()
        assert data["title"] == "Review proposal"
        assert data["description"] == "Review the Q1 proposal document"
        assert data["priority"] == "high"
        assert data["due_date"] == "2024-01-20"
        assert data["source_email_id"] == "msg123"
        assert data["source_thread_id"] == "thread456"
        assert data["confidence"] == 0.95

    def test_to_dict_no_due_date(self):
        """Test serialization without due date."""
        task = ExtractedTask(
            title="Follow up",
            description="Follow up on request",
            priority=Priority.MEDIUM,
            source_email_id="msg123",
            source_thread_id="thread456",
        )

        data = task.to_dict()
        assert data["due_date"] is None

    def test_from_dict(self):
        """Test task deserialization."""
        data = {
            "title": "Review proposal",
            "description": "Review the Q1 proposal document",
            "priority": "high",
            "due_date": "2024-01-20",
            "source_email_id": "msg123",
            "source_thread_id": "thread456",
            "confidence": 0.95,
        }

        task = ExtractedTask.from_dict(data)
        assert task.title == "Review proposal"
        assert task.priority == Priority.HIGH
        assert task.due_date == date(2024, 1, 20)
        assert task.confidence == 0.95

    def test_from_dict_no_due_date(self):
        """Test deserialization without due date."""
        data = {
            "title": "Follow up",
            "description": "Follow up",
            "priority": "low",
            "due_date": None,
            "source_email_id": "msg123",
            "source_thread_id": "thread456",
        }

        task = ExtractedTask.from_dict(data)
        assert task.due_date is None

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = ExtractedTask(
            title="Test task",
            description="Test description",
            priority=Priority.URGENT,
            source_email_id="msg123",
            source_thread_id="thread456",
            due_date=date(2024, 2, 15),
            confidence=0.8,
        )

        restored = ExtractedTask.from_dict(original.to_dict())
        assert restored.title == original.title
        assert restored.priority == original.priority
        assert restored.due_date == original.due_date
        assert restored.confidence == original.confidence

    def test_default_confidence(self):
        """Test default confidence value."""
        task = ExtractedTask(
            title="Test",
            description="Test",
            priority=Priority.LOW,
            source_email_id="msg123",
            source_thread_id="thread456",
        )
        assert task.confidence == 1.0


class TestAnalysisResult:
    """Tests for AnalysisResult dataclass."""

    def test_to_dict(self):
        """Test result serialization."""
        task = ExtractedTask(
            title="Review doc",
            description="Review document",
            priority=Priority.HIGH,
            source_email_id="msg123",
            source_thread_id="thread456",
        )

        result = AnalysisResult(
            email_id="msg123",
            thread_id="thread456",
            summary="Request to review document",
            tasks=[task],
            requires_response=True,
            sender_name="John Doe",
            raw_response='{"summary": "..."}',
        )

        data = result.to_dict()
        assert data["email_id"] == "msg123"
        assert data["summary"] == "Request to review document"
        assert data["requires_response"] is True
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["title"] == "Review doc"

    def test_to_dict_empty_tasks(self):
        """Test serialization with no tasks."""
        result = AnalysisResult(
            email_id="msg123",
            thread_id="thread456",
            summary="Informational email",
        )

        data = result.to_dict()
        assert data["tasks"] == []
        assert data["requires_response"] is False

    def test_from_dict(self):
        """Test result deserialization."""
        data = {
            "email_id": "msg123",
            "thread_id": "thread456",
            "summary": "Request to review",
            "tasks": [
                {
                    "title": "Review doc",
                    "description": "Review document",
                    "priority": "high",
                    "due_date": "2024-01-20",
                    "source_email_id": "msg123",
                    "source_thread_id": "thread456",
                    "confidence": 0.9,
                }
            ],
            "requires_response": True,
            "sender_name": "John",
            "raw_response": "{}",
        }

        result = AnalysisResult.from_dict(data)
        assert result.email_id == "msg123"
        assert result.requires_response is True
        assert len(result.tasks) == 1
        assert result.tasks[0].title == "Review doc"

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        task = ExtractedTask(
            title="Task",
            description="Description",
            priority=Priority.MEDIUM,
            source_email_id="msg123",
            source_thread_id="thread456",
            due_date=date(2024, 3, 1),
        )

        original = AnalysisResult(
            email_id="msg123",
            thread_id="thread456",
            summary="Summary text",
            tasks=[task],
            requires_response=True,
            sender_name="Sender",
        )

        restored = AnalysisResult.from_dict(original.to_dict())
        assert restored.email_id == original.email_id
        assert restored.summary == original.summary
        assert restored.requires_response == original.requires_response
        assert len(restored.tasks) == 1


class TestLLMExceptions:
    """Tests for custom exception classes."""

    def test_rate_limit_with_retry(self):
        """Test LLMRateLimitError with retry_after."""
        error = LLMRateLimitError("Rate limited", retry_after=30.0)
        assert str(error) == "Rate limited"
        assert error.retry_after == 30.0

    def test_rate_limit_without_retry(self):
        """Test LLMRateLimitError without retry_after."""
        error = LLMRateLimitError("Rate limited")
        assert error.retry_after is None

    def test_response_error_with_raw(self):
        """Test LLMResponseError with raw response."""
        error = LLMResponseError("Parse failed", raw_response='{"invalid": json}')
        assert str(error) == "Parse failed"
        assert error.raw_response == '{"invalid": json}'

    def test_response_error_without_raw(self):
        """Test LLMResponseError without raw response."""
        error = LLMResponseError("Parse failed")
        assert error.raw_response is None


class TestOpenAIAdapter:
    """Tests for OpenAIAdapter with mocked OpenAI client."""

    def test_missing_api_key_raises(self):
        """Test that missing API key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(LLMAuthenticationError) as exc_info:
                OpenAIAdapter()
            assert "API key not provided" in str(exc_info.value)

    def test_api_key_from_env(self):
        """Test loading API key from environment."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            adapter = OpenAIAdapter()
            assert adapter._api_key == "test-key"

    def test_api_key_from_param(self):
        """Test API key from constructor parameter."""
        adapter = OpenAIAdapter(api_key="explicit-key")
        assert adapter._api_key == "explicit-key"

    def test_model_name_default(self):
        """Test default model name."""
        adapter = OpenAIAdapter(api_key="test-key")
        assert adapter.model_name == "gpt-4o-mini"

    def test_model_name_custom(self):
        """Test custom model name."""
        adapter = OpenAIAdapter(api_key="test-key", model="gpt-4-turbo")
        assert adapter.model_name == "gpt-4-turbo"

    def test_provider_name(self):
        """Test provider name property."""
        adapter = OpenAIAdapter(api_key="test-key")
        assert adapter.provider_name == "OpenAI"

    def test_complete_success(self):
        """Test successful completion."""
        adapter = OpenAIAdapter(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response text"))]

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            messages = [Message(MessageRole.USER, "Hello")]
            result = adapter.complete(messages)

            assert result == "Response text"

    def test_complete_json_mode(self):
        """Test completion with JSON mode enabled."""
        adapter = OpenAIAdapter(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"key": "value"}'))]

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            messages = [Message(MessageRole.USER, "Return JSON")]
            result = adapter.complete(messages, json_mode=True)

            # Verify json_mode was passed
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_complete_empty_choices_raises(self):
        """Test that empty choices raises error."""
        adapter = OpenAIAdapter(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = []

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            with pytest.raises(LLMResponseError) as exc_info:
                adapter.complete([Message(MessageRole.USER, "Hello")])
            assert "No choices" in str(exc_info.value)

    def test_lazy_client_init(self):
        """Test that client is lazily initialized."""
        adapter = OpenAIAdapter(api_key="test-key")
        assert adapter._client is None

        # Client should be created on first access
        with patch("src.analyzer.openai_adapter.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            client = adapter._get_client()
            assert client is not None
            mock_openai.assert_called_once()


class TestEmailAnalyzer:
    """Tests for EmailAnalyzer with mocked adapter."""

    @pytest.fixture
    def sample_email(self):
        """Create a sample Email object for testing."""
        return Email(
            id="msg123",
            thread_id="thread456",
            subject="Project Update - Action Required",
            sender="John Doe",
            sender_email="john@example.com",
            recipient="me@example.com",
            date=datetime(2024, 1, 15, 10, 30),
            body="Hi, please review the attached proposal by Friday. This is urgent.",
        )

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock LLMAdapter."""
        adapter = MagicMock(spec=LLMAdapter)
        adapter.model_name = "test-model"
        adapter.provider_name = "test-provider"
        return adapter

    @pytest.fixture
    def valid_llm_response(self):
        """Sample valid LLM JSON response."""
        return json.dumps(
            {
                "summary": "Request to review proposal by Friday",
                "requires_response": True,
                "tasks": [
                    {
                        "title": "Review proposal",
                        "description": "Review the attached proposal document",
                        "due_date": "2024-01-19",
                        "priority": "urgent",
                        "confidence": 0.95,
                    }
                ],
            }
        )

    def test_analyze_extracts_tasks(self, sample_email, mock_adapter, valid_llm_response):
        """Test that analyze extracts tasks correctly."""
        mock_adapter.complete.return_value = valid_llm_response

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        result = analyzer.analyze(sample_email)

        assert result.email_id == "msg123"
        assert result.thread_id == "thread456"
        assert result.summary == "Request to review proposal by Friday"
        assert result.requires_response is True
        assert len(result.tasks) == 1
        assert result.tasks[0].title == "Review proposal"
        assert result.tasks[0].priority == Priority.URGENT
        assert result.tasks[0].due_date == date(2024, 1, 19)
        assert result.tasks[0].source_email_id == "msg123"

    def test_analyze_no_tasks(self, sample_email, mock_adapter):
        """Test analyzing email with no tasks."""
        response = json.dumps(
            {
                "summary": "FYI newsletter",
                "requires_response": False,
                "tasks": [],
            }
        )
        mock_adapter.complete.return_value = response

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        result = analyzer.analyze(sample_email)

        assert result.summary == "FYI newsletter"
        assert result.requires_response is False
        assert len(result.tasks) == 0

    def test_analyze_multiple_tasks(self, sample_email, mock_adapter):
        """Test analyzing email with multiple tasks."""
        response = json.dumps(
            {
                "summary": "Meeting request with multiple action items",
                "requires_response": True,
                "tasks": [
                    {
                        "title": "Review agenda",
                        "description": "Review meeting agenda",
                        "priority": "high",
                        "due_date": "2024-01-16",
                        "confidence": 0.9,
                    },
                    {
                        "title": "Prepare slides",
                        "description": "Prepare presentation slides",
                        "priority": "medium",
                        "due_date": "2024-01-17",
                        "confidence": 0.85,
                    },
                ],
            }
        )
        mock_adapter.complete.return_value = response

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        result = analyzer.analyze(sample_email)

        assert len(result.tasks) == 2
        assert result.tasks[0].title == "Review agenda"
        assert result.tasks[1].title == "Prepare slides"

    def test_retry_on_parse_error(self, sample_email, mock_adapter, valid_llm_response):
        """Test that analyzer retries on parse errors."""
        # First call returns invalid JSON, second returns valid
        mock_adapter.complete.side_effect = [
            "not valid json",
            valid_llm_response,
        ]

        analyzer = EmailAnalyzer(adapter=mock_adapter, max_retries=2)
        result = analyzer.analyze(sample_email)

        assert result.summary == "Request to review proposal by Friday"
        assert mock_adapter.complete.call_count == 2

    def test_max_retries_exceeded(self, sample_email, mock_adapter):
        """Test that LLMResponseError is raised after max retries."""
        mock_adapter.complete.return_value = "always invalid json"

        analyzer = EmailAnalyzer(adapter=mock_adapter, max_retries=2)

        with pytest.raises(LLMResponseError):
            analyzer.analyze(sample_email)

        # Should have tried 3 times (1 + 2 retries)
        assert mock_adapter.complete.call_count == 3

    def test_custom_prompts(self, sample_email, mock_adapter, valid_llm_response):
        """Test analyzer with custom prompts."""
        mock_adapter.complete.return_value = valid_llm_response

        analyzer = EmailAnalyzer(
            adapter=mock_adapter,
            system_prompt="Custom system prompt",
            user_prompt_template="Custom: {subject}\n{body}",
        )
        analyzer.analyze(sample_email)

        # Verify custom prompts were used
        call_args = mock_adapter.complete.call_args
        messages = call_args[1]["messages"]
        assert messages[0].content == "Custom system prompt"
        assert "Custom:" in messages[1].content

    def test_truncates_long_emails(self, mock_adapter, valid_llm_response):
        """Test that long email bodies are truncated."""
        mock_adapter.complete.return_value = valid_llm_response

        long_body = "x" * 10000
        email = Email(
            id="msg123",
            thread_id="thread456",
            subject="Test",
            sender="Test",
            sender_email="test@example.com",
            recipient="me@example.com",
            date=datetime(2024, 1, 15),
            body=long_body,
        )

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        analyzer.analyze(email)

        call_args = mock_adapter.complete.call_args
        messages = call_args[1]["messages"]
        # Body should be truncated in user message
        assert len(messages[1].content) < len(long_body)

    def test_default_adapter_creation(self, sample_email):
        """Test that default OpenAI adapter is created."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            analyzer = EmailAnalyzer()
            adapter = analyzer.adapter

            assert isinstance(adapter, OpenAIAdapter)

    def test_batch_analyze(self, mock_adapter, valid_llm_response):
        """Test batch analysis of multiple emails."""
        mock_adapter.complete.return_value = valid_llm_response

        emails = [
            Email(
                id=f"msg{i}",
                thread_id=f"thread{i}",
                subject=f"Subject {i}",
                sender="Test",
                sender_email="test@example.com",
                recipient="me@example.com",
                date=datetime(2024, 1, 15),
                body="Body",
            )
            for i in range(3)
        ]

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        results = analyzer.analyze_batch(emails)

        assert len(results) == 3
        assert results[0].email_id == "msg0"
        assert results[1].email_id == "msg1"
        assert results[2].email_id == "msg2"

    def test_adapter_property(self, mock_adapter):
        """Test accessing adapter property."""
        analyzer = EmailAnalyzer(adapter=mock_adapter)
        assert analyzer.adapter is mock_adapter


class TestResponseParsing:
    """Tests for JSON response parsing edge cases."""

    @pytest.fixture
    def sample_email(self):
        """Create a sample Email for testing."""
        return Email(
            id="msg123",
            thread_id="thread456",
            subject="Test",
            sender="Test",
            sender_email="test@example.com",
            recipient="me@example.com",
            date=datetime(2024, 1, 15),
            body="Test body",
        )

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock LLMAdapter."""
        return MagicMock(spec=LLMAdapter)

    def test_valid_json(self, sample_email, mock_adapter):
        """Test parsing valid JSON response."""
        mock_adapter.complete.return_value = json.dumps(
            {"summary": "Test", "requires_response": False, "tasks": []}
        )

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        result = analyzer.analyze(sample_email)
        assert result.summary == "Test"

    def test_invalid_json_raises(self, sample_email, mock_adapter):
        """Test that invalid JSON raises LLMResponseError."""
        mock_adapter.complete.return_value = "not json at all"

        analyzer = EmailAnalyzer(adapter=mock_adapter, max_retries=0)
        with pytest.raises(LLMResponseError) as exc_info:
            analyzer.analyze(sample_email)
        assert "Failed to parse" in str(exc_info.value)

    def test_missing_fields_defaults(self, sample_email, mock_adapter):
        """Test that missing fields get defaults."""
        mock_adapter.complete.return_value = json.dumps({})

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        result = analyzer.analyze(sample_email)

        assert result.summary == ""
        assert result.requires_response is False
        assert result.tasks == []

    def test_invalid_priority_defaults(self, sample_email, mock_adapter):
        """Test that invalid priority defaults to medium."""
        mock_adapter.complete.return_value = json.dumps(
            {
                "summary": "Test",
                "tasks": [
                    {
                        "title": "Task",
                        "description": "Desc",
                        "priority": "invalid_priority",
                        "due_date": None,
                    }
                ],
            }
        )

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        result = analyzer.analyze(sample_email)

        # Task should be skipped due to invalid priority
        assert len(result.tasks) == 0

    def test_invalid_date_skips_task(self, sample_email, mock_adapter):
        """Test that invalid date format skips the task."""
        mock_adapter.complete.return_value = json.dumps(
            {
                "summary": "Test",
                "tasks": [
                    {
                        "title": "Task",
                        "description": "Desc",
                        "priority": "high",
                        "due_date": "not-a-date",
                    }
                ],
            }
        )

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        result = analyzer.analyze(sample_email)

        # Task should be skipped due to invalid date
        assert len(result.tasks) == 0

    def test_missing_task_title_skips(self, sample_email, mock_adapter):
        """Test that task without title is skipped."""
        mock_adapter.complete.return_value = json.dumps(
            {
                "summary": "Test",
                "tasks": [
                    {
                        "description": "Desc",
                        "priority": "high",
                    }
                ],
            }
        )

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        result = analyzer.analyze(sample_email)

        assert len(result.tasks) == 0

    def test_stores_raw_response(self, sample_email, mock_adapter):
        """Test that raw response is stored for debugging."""
        raw = json.dumps({"summary": "Test", "tasks": []})
        mock_adapter.complete.return_value = raw

        analyzer = EmailAnalyzer(adapter=mock_adapter)
        result = analyzer.analyze(sample_email)

        assert result.raw_response == raw
