"""Main EmailAnalyzer class for analyzing emails with LLM."""

import json
from datetime import date
from typing import Optional

from src.fetcher import Email

from .adapter import LLMAdapter
from .exceptions import LLMResponseError
from .models import AnalysisResult, ExtractedTask, Message, MessageRole, Priority
from .openai_adapter import OpenAIAdapter
from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


class EmailAnalyzer:
    """Analyzes emails using an LLM to extract tasks and summaries.

    The analyzer uses a pluggable LLM adapter pattern, allowing different
    LLM providers (OpenAI, Anthropic, local models) to be swapped without
    changing the analysis logic.

    Example usage:
        analyzer = EmailAnalyzer()  # Uses OpenAI by default
        result = analyzer.analyze(email)
        for task in result.tasks:
            print(f"Task: {task.title} (Priority: {task.priority})")

    With custom adapter:
        adapter = AnthropicAdapter(api_key="...")
        analyzer = EmailAnalyzer(adapter=adapter)
    """

    MAX_BODY_LENGTH = 8000

    def __init__(
        self,
        adapter: Optional[LLMAdapter] = None,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 2,
    ):
        """Initialize the EmailAnalyzer.

        Args:
            adapter: LLM adapter to use. Defaults to OpenAIAdapter.
            system_prompt: Custom system prompt. Defaults to built-in prompt.
            user_prompt_template: Custom user prompt template.
                Must contain placeholders: {sender_name}, {sender_email},
                {recipient}, {subject}, {date}, {body}
            temperature: LLM sampling temperature (0.0 = deterministic).
            max_retries: Number of retries on transient failures.
        """
        self._adapter = adapter
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        self._user_prompt_template = user_prompt_template or USER_PROMPT_TEMPLATE
        self._temperature = temperature
        self._max_retries = max_retries

    def _get_adapter(self) -> LLMAdapter:
        """Get LLM adapter, creating default if needed (lazy init)."""
        if self._adapter is None:
            self._adapter = OpenAIAdapter()
        return self._adapter

    def _build_messages(self, email: Email) -> list[Message]:
        """Build LLM messages from email.

        Args:
            email: Email object to analyze.

        Returns:
            List of messages for LLM.
        """
        body = email.body[: self.MAX_BODY_LENGTH]

        user_content = self._user_prompt_template.format(
            sender_name=email.sender,
            sender_email=email.sender_email,
            recipient=email.recipient,
            subject=email.subject,
            date=email.date.strftime("%Y-%m-%d %H:%M"),
            body=body,
        )

        return [
            Message(role=MessageRole.SYSTEM, content=self._system_prompt),
            Message(role=MessageRole.USER, content=user_content),
        ]

    def _parse_response(self, response: str, email: Email) -> AnalysisResult:
        """Parse LLM JSON response into AnalysisResult.

        Args:
            response: Raw JSON string from LLM.
            email: Original email for source linking.

        Returns:
            Parsed AnalysisResult.

        Raises:
            LLMResponseError: If response cannot be parsed as JSON.
        """
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            raise LLMResponseError(
                f"Failed to parse LLM response as JSON: {e}",
                raw_response=response,
            ) from e

        tasks = []
        for task_data in data.get("tasks", []):
            try:
                due_date = None
                if task_data.get("due_date"):
                    due_date = date.fromisoformat(task_data["due_date"])

                task = ExtractedTask(
                    title=task_data["title"],
                    description=task_data.get("description", ""),
                    due_date=due_date,
                    priority=Priority(task_data.get("priority", "medium")),
                    source_email_id=email.id,
                    source_thread_id=email.thread_id,
                    confidence=float(task_data.get("confidence", 1.0)),
                    source_email_subject=email.subject,
                    source_sender=email.sender,
                )
                tasks.append(task)
            except (KeyError, ValueError):
                # Skip malformed tasks but continue with others
                continue

        return AnalysisResult(
            email_id=email.id,
            thread_id=email.thread_id,
            summary=data.get("summary", ""),
            tasks=tasks,
            requires_response=data.get("requires_response", False),
            sender_name=email.sender,
            raw_response=response,
        )

    def analyze(self, email: Email) -> AnalysisResult:
        """Analyze an email to extract tasks and summary.

        Args:
            email: Email object to analyze.

        Returns:
            AnalysisResult containing summary and extracted tasks.

        Raises:
            LLMConnectionError: Failed to connect to LLM provider.
            LLMRateLimitError: Rate limit exceeded.
            LLMAuthenticationError: Invalid credentials.
            LLMResponseError: Invalid response after retries.
        """
        adapter = self._get_adapter()
        messages = self._build_messages(email)

        last_error: Optional[LLMResponseError] = None
        for attempt in range(self._max_retries + 1):
            try:
                response = adapter.complete(
                    messages=messages,
                    temperature=self._temperature,
                    json_mode=True,
                )
                return self._parse_response(response, email)
            except LLMResponseError as e:
                last_error = e
                if attempt < self._max_retries:
                    continue
                raise

        # Should not reach here, but satisfy type checker
        if last_error:
            raise last_error
        raise LLMResponseError("Analysis failed with no error details")

    def analyze_batch(self, emails: list[Email]) -> list[AnalysisResult]:
        """Analyze multiple emails.

        Processes emails sequentially. For parallel processing,
        consider using concurrent.futures in the caller.

        Args:
            emails: List of Email objects to analyze.

        Returns:
            List of AnalysisResult objects (same order as input).
        """
        return [self.analyze(email) for email in emails]

    @property
    def adapter(self) -> LLMAdapter:
        """Access the LLM adapter."""
        return self._get_adapter()
