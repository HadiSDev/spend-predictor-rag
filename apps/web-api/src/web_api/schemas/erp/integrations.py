"""ERP integrations as read, created and updated."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ErpIntegrationRead(BaseModel):
    """Non-secret view of an integration."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    erp_type: str
    label: str | None = None
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    created_at: datetime
    has_credentials: bool = False


class ErpIntegrationCreate(BaseModel):
    """Connect an integration."""

    company_id: str
    erp_type: str = Field(min_length=1)
    label: str | None = None
    credentials: dict = Field(default_factory=dict)


class ErpIntegrationUpdate(BaseModel):
    """Partial update."""

    label: str | None = None
    credentials: dict | None = None
