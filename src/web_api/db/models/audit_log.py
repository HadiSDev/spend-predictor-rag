"""Append-only audit trail for domain changes.

One generic table records changes to auditable entities (currently ``invoice``
and ``invoice_line``) rather than a separate audit table per entity. Each row is
an immutable event: who (``actor`` — a user id, or the sentinel ``system`` for
automated/AI changes), what (``entity_type``/``entity_id`` + ``action``), and
the per-field ``changes`` (old → new). History is reconstructed by reading all
rows for an entity in ``created_at`` order; rows are never updated or deleted.

Tenant scope is derived through the referenced entity's company — the audit row
itself stores no organization id, callers resolve ownership via the entity.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, String
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid

# Sentinel actor for automated / AI-driven changes (vs. a real user id).
SYSTEM_ACTOR = "system"


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: str = Field(default_factory=_uuid, primary_key=True)
    # e.g. "invoice", "invoice_line". Kept as a plain string (no FK) so one table
    # can reference many entity types.
    entity_type: str = Field(sa_type=String, nullable=False)
    entity_id: str = Field(sa_type=String, nullable=False, index=True)
    # e.g. "ai_categorize", "verify", "edit".
    action: str = Field(sa_type=String, nullable=False)
    # User id, or SYSTEM_ACTOR for automated changes.
    actor: str = Field(sa_type=String, nullable=False)
    # List of {"field": str, "old": Any, "new": Any}.
    changes: Optional[list] = Field(sa_type=JSON, nullable=True)
    created_at: datetime = Field(sa_column=_ts())
