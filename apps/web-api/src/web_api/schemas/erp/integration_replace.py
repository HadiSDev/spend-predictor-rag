"""Provisioning an ERP connection, and replacing one with another."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class IntegrationSpec(BaseModel):
    """An ERP connection to provision."""

    erp_type: str = Field(min_length=1)
    label: str | None = None
    credentials: dict = Field(default_factory=dict)


class IntegrationReplace(IntegrationSpec):
    """Replace a company's ERP connection with a different system."""

    confirm: bool = False


class IntegrationReplaceBlocked(BaseModel):
    """Why a replacement needs confirming: what the outgoing ERP already posted."""

    detail: str
    invoices: int
    entries: int
    earliest: date | None = None
    latest: date | None = None
