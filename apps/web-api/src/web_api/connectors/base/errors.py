"""The error vocabulary every connector raises."""
from __future__ import annotations


class ErpConnectionError(Exception):
    """Network error, timeout, unreachable host."""


class ErpAuthError(Exception):
    """Invalid or expired credentials."""


class ErpRateLimitError(Exception):
    """Rate-limited by ERP."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ErpDataError(Exception):
    """Malformed or unexpected data from ERP."""
