"""Results of company-wide maintenance actions."""
from __future__ import annotations

from pydantic import BaseModel


class FxRecomputeResult(BaseModel):
    """What a recompute did."""

    company_id: str
    base_currency: str
    converted: int
    unconverted: int
    unchanged: int


class RecategorizeResult(BaseModel):
    """How many lines were returned to the categorizer's queue."""

    company_id: str
    queued: int
