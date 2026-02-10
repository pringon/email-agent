"""Data models for pipeline execution results."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class StepResult:
    """Result of a single pipeline step."""

    name: str
    success: bool
    duration_seconds: float
    details: dict[str, Any]
    error: str | None = None


@dataclass
class PipelineResult:
    """Aggregate result of a full pipeline run."""

    started_at: datetime
    finished_at: datetime | None = None
    steps: list[StepResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return all(step.success for step in self.steps)
