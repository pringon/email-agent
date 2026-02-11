"""ReplyResolver for LLM-based task resolution from sent replies."""

import json
import logging
from typing import Optional

from src.analyzer.adapter import LLMAdapter
from src.analyzer.exceptions import LLMResponseError
from src.analyzer.models import Message, MessageRole
from src.analyzer.openai_adapter import OpenAIAdapter
from src.tasks.models import Task

from .prompts import (
    REPLY_RESOLVER_SYSTEM_PROMPT,
    REPLY_RESOLVER_USER_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)


class ReplyResolver:
    """Uses an LLM to determine which tasks a sent reply addresses.

    Given the text of a sent reply and a list of open tasks for the
    same email thread, asks the LLM to identify which tasks the reply
    actually resolves.

    Example usage:
        resolver = ReplyResolver()
        resolved_ids = resolver.resolve(
            reply_body="I've reviewed the proposal and approved it.",
            subject="Re: Q1 Proposal",
            tasks=open_tasks,
        )
    """

    MAX_REPLY_LENGTH = 8000

    def __init__(
        self,
        adapter: Optional[LLMAdapter] = None,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 2,
    ):
        """Initialize the ReplyResolver.

        Args:
            adapter: LLM adapter to use. Defaults to OpenAIAdapter.
            system_prompt: Custom system prompt.
            user_prompt_template: Custom user prompt template.
                Must contain placeholders: {subject}, {reply_body}, {tasks_list}
            temperature: LLM sampling temperature (0.0 = deterministic).
            max_retries: Number of retries on transient failures.
        """
        self._adapter = adapter
        self._system_prompt = system_prompt or REPLY_RESOLVER_SYSTEM_PROMPT
        self._user_prompt_template = (
            user_prompt_template or REPLY_RESOLVER_USER_PROMPT_TEMPLATE
        )
        self._temperature = temperature
        self._max_retries = max_retries

    def _get_adapter(self) -> LLMAdapter:
        """Get LLM adapter, creating default if needed."""
        if self._adapter is None:
            self._adapter = OpenAIAdapter()
        return self._adapter

    def _format_tasks_list(self, tasks: list[Task]) -> str:
        """Format tasks into a string for the LLM prompt.

        Args:
            tasks: List of Task objects.

        Returns:
            Formatted string with one task per line.
        """
        lines = []
        for task in tasks:
            # Extract a brief notes excerpt (strip metadata section)
            notes_excerpt = ""
            if task.notes:
                notes_excerpt = task.notes.split(Task.METADATA_PREFIX)[0].strip()
                if len(notes_excerpt) > 200:
                    notes_excerpt = notes_excerpt[:200] + "..."

            parts = [f"Task ID: {task.id}", f"Title: {task.title}"]
            if notes_excerpt:
                parts.append(f"Description: {notes_excerpt}")
            lines.append("- " + " | ".join(parts))

        return "\n".join(lines)

    def _build_messages(
        self, reply_body: str, subject: str, tasks: list[Task]
    ) -> list[Message]:
        """Build LLM messages for reply resolution.

        Args:
            reply_body: Plain text body of the sent reply.
            subject: Email subject line.
            tasks: List of open Task objects.

        Returns:
            List of messages for LLM.
        """
        body = reply_body[: self.MAX_REPLY_LENGTH]
        tasks_list = self._format_tasks_list(tasks)

        user_content = self._user_prompt_template.format(
            subject=subject,
            reply_body=body,
            tasks_list=tasks_list,
        )

        return [
            Message(role=MessageRole.SYSTEM, content=self._system_prompt),
            Message(role=MessageRole.USER, content=user_content),
        ]

    def _parse_response(self, response: str, tasks: list[Task]) -> list[str]:
        """Parse LLM JSON response into list of resolved task IDs.

        Args:
            response: Raw JSON string from LLM.
            tasks: Original task list for ID validation.

        Returns:
            List of task IDs that the reply resolves.

        Raises:
            LLMResponseError: If response cannot be parsed as JSON.
        """
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            raise LLMResponseError(
                f"Failed to parse reply resolver response as JSON: {e}",
                raw_response=response,
            ) from e

        valid_ids = {t.id for t in tasks if t.id}
        resolved_ids = []

        for entry in data.get("resolved_tasks", []):
            try:
                task_id = entry["task_id"]
                resolved = entry["resolved"]
                if resolved and task_id in valid_ids:
                    resolved_ids.append(task_id)
            except (KeyError, TypeError) as e:
                logger.warning("Skipping malformed resolved_task entry %r: %s", entry, e)
                continue

        return resolved_ids

    def resolve(
        self, reply_body: str, subject: str, tasks: list[Task]
    ) -> list[str]:
        """Analyze reply against tasks and return IDs of resolved tasks.

        Args:
            reply_body: Plain text body of the sent reply.
            subject: Email subject for context.
            tasks: List of open Task objects for this thread.

        Returns:
            List of task IDs that the reply resolves. May be empty
            if no tasks are addressed.

        Raises:
            LLMConnectionError: Failed to connect to LLM provider.
            LLMRateLimitError: Rate limit exceeded.
            LLMAuthenticationError: Invalid credentials.
            LLMResponseError: Invalid response after retries.
        """
        if not tasks:
            return []

        adapter = self._get_adapter()
        messages = self._build_messages(reply_body, subject, tasks)

        last_error: Optional[LLMResponseError] = None
        for attempt in range(self._max_retries + 1):
            try:
                response = adapter.complete(
                    messages=messages,
                    temperature=self._temperature,
                    json_mode=True,
                )
                return self._parse_response(response, tasks)
            except LLMResponseError as e:
                last_error = e
                if attempt < self._max_retries:
                    continue
                raise

        if last_error:
            raise last_error
        raise LLMResponseError("Reply resolution failed with no error details")
