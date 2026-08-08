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

from sqlalchemy import BigInteger, Column, JSON, String, event, func, select
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
    # True insertion order — independent of `created_at`, which on PostgreSQL
    # is constant for the whole transaction (so rows written together always
    # tie), and independent of `id`, a random UUID unrelated to write order.
    # A feed that needs "what happened, in order" needs this column, not those
    # two.
    #
    # PostgreSQL fills it itself from a real sequence (see the
    # `0019_audit_log_seq` migration) — atomic, so it stays correct under
    # concurrent writers on multiple app instances. SQLite has no equivalent
    # for an autoincrementing column that isn't the table's sole INTEGER
    # PRIMARY KEY (verified directly: neither `Identity()` nor a subquery
    # `server_default` are accepted there for a secondary column), so
    # `_assign_seq_on_sqlite` below supplies the same guarantee for it; the
    # guard means it never runs — and never competes with the real
    # sequence — on PostgreSQL.
    seq: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, nullable=True, unique=True)
    )


@event.listens_for(AuditLog, "before_insert")
def _assign_seq_on_sqlite(mapper, connection, target: "AuditLog") -> None:
    """SQLite fallback for `seq`. Only fires when nothing has already set it —
    i.e. on the SQLite engine the test suite runs against, where the column
    has no server-side default (see the field comment above)."""
    if connection.dialect.name != "sqlite" or target.seq is not None:
        return
    current_max = connection.execute(select(func.max(AuditLog.__table__.c.seq))).scalar()
    target.seq = (current_max or 0) + 1
