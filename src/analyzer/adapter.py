"""Abstract interface for LLM adapters."""

from abc import ABC, abstractmethod

from .models import Message


class LLMAdapter(ABC):
    """Abstract base class for LLM provider adapters.

    Implementations should handle:
    - API authentication
    - Request formatting for specific provider
    - Response parsing to common format
    - Error handling and translation to custom exceptions

    To implement a new adapter:
    1. Subclass LLMAdapter
    2. Implement complete(), model_name, and provider_name
    3. Map provider-specific exceptions to exceptions from exceptions.py

    Example usage:
        adapter = OpenAIAdapter(api_key="...")
        messages = [
            Message(MessageRole.SYSTEM, "You are a helpful assistant."),
            Message(MessageRole.USER, "Analyze this email..."),
        ]
        response = adapter.complete(messages, json_mode=True)
    """

    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        """Send messages to LLM and get completion.

        Args:
            messages: List of conversation messages.
            temperature: Sampling temperature (0.0 = deterministic).
            max_tokens: Maximum tokens in response.
            json_mode: If True, request JSON-formatted output.

        Returns:
            The LLM's response text.

        Raises:
            LLMConnectionError: Failed to connect to provider.
            LLMRateLimitError: Rate limit exceeded.
            LLMAuthenticationError: Invalid credentials.
            LLMResponseError: Invalid response from provider.
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the name of the model being used."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of the LLM provider."""
        pass
