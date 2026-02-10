"""Pipeline orchestrator for the email agent.

Connects EmailFetcher, EmailAnalyzer, and TaskManager into a single
pipeline run with per-step error isolation and structured results.
"""

from .models import PipelineResult, StepResult
from .pipeline import EmailAgentOrchestrator

__all__ = [
    "EmailAgentOrchestrator",
    "PipelineResult",
    "StepResult",
]
