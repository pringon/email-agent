"""OpenAI GPT adapter implementation."""

import logging
import os
from typing import Optional

from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from .adapter import LLMAdapter
from .exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
)
from .models import Message

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMAdapter):
    """LLM adapter for OpenAI GPT models.

    Supports GPT-4o-mini, GPT-4o, GPT-4-turbo, and GPT-3.5-turbo models.
    Uses lazy initialization for the OpenAI client.

    Example usage:
        adapter = OpenAIAdapter()  # Uses OPENAI_API_KEY env var
        adapter = OpenAIAdapter(api_key="sk-...", model="gpt-4o")
    """

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        organization: Optional[str] = None,
    ):
        """Initialize the OpenAI adapter.

        Args:
            api_key: OpenAI API key. Defaults to OPENAI_API_KEY env var.
            model: Model to use. Defaults to gpt-4o-mini.
            organization: Optional OpenAI organization ID.

        Raises:
            LLMAuthenticationError: If no API key is available.
        """
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self._api_key:
            raise LLMAuthenticationError(
                "OpenAI API key not provided. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self._model = model or self.DEFAULT_MODEL
        self._organization = organization
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        """Get or create OpenAI client (lazy initialization)."""
        if self._client is None:
            self._client = OpenAI(
                api_key=self._api_key,
                organization=self._organization,
            )
        return self._client

    def complete(
        self,
        messages: list[Message],
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        """Send messages to OpenAI and get completion.

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 = deterministic).
            max_tokens: Maximum tokens in response.
            json_mode: If True, request JSON-formatted output.

        Returns:
            The model's response text.

        Raises:
            LLMConnectionError: Failed to connect to OpenAI.
            LLMRateLimitError: Rate limit exceeded.
            LLMAuthenticationError: Invalid API key.
            LLMResponseError: Invalid response from OpenAI.
        """
        client = self._get_client()
        logger.debug("Sending request to OpenAI model=%s json_mode=%s", self._model, json_mode)

        try:
            response_format = {"type": "json_object"} if json_mode else {"type": "text"}

            response = client.chat.completions.create(
                model=self._model,
                messages=[m.to_dict() for m in messages],  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,  # type: ignore[arg-type]
            )

            if not response.choices:
                raise LLMResponseError("No choices in OpenAI response")

            content = response.choices[0].message.content
            if content is None:
                raise LLMResponseError("Empty content in OpenAI response")

            if response.usage:
                logger.debug(
                    "OpenAI response received (prompt=%d, completion=%d tokens)",
                    response.usage.prompt_tokens, response.usage.completion_tokens,
                )

            return content

        except AuthenticationError as e:
            raise LLMAuthenticationError(f"OpenAI authentication failed: {e}") from e
        except RateLimitError as e:
            retry_after = None
            if hasattr(e, "response") and e.response:
                retry_header = e.response.headers.get("retry-after")
                if retry_header:
                    retry_after = float(retry_header)
            raise LLMRateLimitError(
                f"OpenAI rate limit exceeded: {e}", retry_after
            ) from e
        except APIConnectionError as e:
            raise LLMConnectionError(f"Failed to connect to OpenAI: {e}") from e
        except APIError as e:
            raise LLMResponseError(f"OpenAI API error: {e}") from e

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "OpenAI"
