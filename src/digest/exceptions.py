"""Exceptions for the digest reporter module."""


class DigestError(Exception):
    """Base exception for digest reporter errors."""

    pass


class DigestBuildError(DigestError):
    """Raised when unable to build the digest report."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Failed to build digest report: {reason}")


class DigestDeliveryError(DigestError):
    """Raised when unable to deliver the digest."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Failed to deliver digest: {reason}")
