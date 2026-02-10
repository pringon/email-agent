"""Digest reporter module for generating daily task summaries.

This module compiles pending tasks into daily digest reports,
formatted as plain text or delivered via email.

Public API:
    DigestReporter: Main class for generating and delivering digests.
    DigestReport: Structured digest report data.
    DigestSection: A section grouping related tasks.
    DeliveryResult: Result of a digest delivery operation.
    DigestError: Base exception for module errors.
    DigestBuildError: Raised when report cannot be built.
    DigestDeliveryError: Raised when delivery fails.
"""

from .digest_reporter import DigestReporter
from .exceptions import DigestBuildError, DigestDeliveryError, DigestError
from .models import DeliveryResult, DigestReport, DigestSection

__all__ = [
    "DigestReporter",
    "DigestReport",
    "DigestSection",
    "DeliveryResult",
    "DigestError",
    "DigestBuildError",
    "DigestDeliveryError",
]
