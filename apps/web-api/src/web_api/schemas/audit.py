"""Audit-trail rows."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    action: str
    actor: str
    changes: list | None = None
    created_at: datetime


class VoucherAuditRead(AuditLogRead):
    """An audit row with the thing it happened to already named."""

    entity_label: str
