"""Email analyzer module for extracting tasks from emails using LLM.

This module provides the EmailAnalyzer class and supporting components
for analyzing emails and extracting actionable tasks.

Public API:
    - EmailAnalyzer: Main class for analyzing emails
    - AnalysisResult: Result of email analysis
    - ExtractedTask: A task extracted from an email
    - Priority: Task priority enum
    - LLMAdapter: Interface for LLM providers (for custom implementations)
    - OpenAIAdapter: OpenAI GPT implementation

Example:
    from src.analyzer import EmailAnalyzer
    from src.fetcher import Email

    analyzer = EmailAnalyzer()
    result = analyzer.analyze(email)
    for task in result.tasks:
        print(f"Task: {task.title} (Priority: {task.priority.value})")
"""

from .adapter import LLMAdapter
from .email_analyzer import EmailAnalyzer
from .exceptions import (
    AnalyzerError,
    LLMAuthenticationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
)
from .models import AnalysisResult, EmailType, ExtractedTask, Message, MessageRole, Priority
from .openai_adapter import OpenAIAdapter

__all__ = [
    # Main classes
    "EmailAnalyzer",
    "LLMAdapter",
    "OpenAIAdapter",
    # Models
    "AnalysisResult",
    "EmailType",
    "ExtractedTask",
    "Message",
    "MessageRole",
    "Priority",
    # Exceptions
    "AnalyzerError",
    "LLMAuthenticationError",
    "LLMConnectionError",
    "LLMRateLimitError",
    "LLMResponseError",
]
