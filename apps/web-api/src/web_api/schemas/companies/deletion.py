"""What deleting a company would destroy, or destroyed."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class CompanyRecordCounts(BaseModel):
    """What a company holds, or held."""

    invoices: int
    lines: int
    entries: int
    integrations: int
    earliest: date | None = None
    latest: date | None = None


class CompanyDeleteBlocked(CompanyRecordCounts):
    """Why deleting a company needs confirming: what it would destroy."""

    detail: str


class CompanyDeleteResult(CompanyRecordCounts):
    """What a completed deletion destroyed."""

    id: str
    name: str
