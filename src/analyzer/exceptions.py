"""Custom exceptions for the analyzer module."""

from typing import Optional


class AnalyzerError(Exception):
    """Base exception for analyzer errors."""

    pass


class LLMConnectionError(AnalyzerError):
    """Failed to connect to LLM provider."""

    pass


class LLMRateLimitError(AnalyzerError):
    """Rate limit exceeded on LLM provider.

    Attributes:
        retry_after: Seconds to wait before retrying, if provided by the API.
    """

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMResponseError(AnalyzerError):
    """LLM returned an invalid or unparseable response.

    Attributes:
        raw_response: The original response that failed to parse.
    """

    def __init__(self, message: str, raw_response: Optional[str] = None):
        super().__init__(message)
        self.raw_response = raw_response


class LLMAuthenticationError(AnalyzerError):
    """Authentication failed with LLM provider."""

    pass
