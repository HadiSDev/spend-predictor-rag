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

from sqlalchemy import BigInteger, Column, FetchedValue, JSON, String, UniqueConstraint, event, func, select
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid

# Sentinel actor for automated / AI-driven changes (vs. a real user id).
SYSTEM_ACTOR = "system"

# Per-DBAPI-connection cache key for `_assign_seq_on_sqlite`'s counter. See
# that function for why a per-flush `MAX(seq)` read is wrong.
_SQLITE_SEQ_COUNTER_KEY = "web_api_audit_log_next_seq"


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    # Named to match the migration's constraint exactly (`uq_audit_log_seq`),
    # rather than `Column(unique=True)`'s auto-generated name — otherwise
    # `alembic autogenerate` would see a permanent, spurious diff between the
    # model and the database.
    __table_args__ = (UniqueConstraint("seq", name="uq_audit_log_seq"),)

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
    # concurrent writers on multiple app instances. `nullable=False` here
    # matches what that migration leaves the database in (do not drift).
    #
    # `server_default=FetchedValue()` is what makes this safe: SQLModel's
    # `default=None` (needed so callers can construct an `AuditLog` without
    # naming `seq`) would otherwise leave the attribute *explicitly* set to
    # `None`, and SQLAlchemy sends an explicit value as an explicit `NULL` in
    # the INSERT — bypassing the column's real default and violating the
    # NOT NULL constraint on PostgreSQL. `FetchedValue()` tells SQLAlchemy a
    # server-side default exists (without describing it — the migration
    # already created it), which is what makes a `None` Python value get
    # *omitted* from the INSERT instead, so PostgreSQL's `nextval()` default
    # applies. It renders no DDL of its own, so SQLite's `create_all()` (the
    # test suite) is unaffected — SQLite has no equivalent for an
    # autoincrementing column that isn't the table's sole INTEGER PRIMARY KEY
    # (verified directly: neither `Identity()` nor a subquery `server_default`
    # are accepted there for a secondary column), so
    # `_assign_seq_on_sqlite` below supplies the same guarantee there instead;
    # the dialect guard means it never runs, and never competes with the real
    # sequence, on PostgreSQL.
    seq: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=False, server_default=FetchedValue()),
    )


@event.listens_for(AuditLog, "before_insert")
def _assign_seq_on_sqlite(mapper, connection, target: "AuditLog") -> None:
    """SQLite fallback for `seq`. Only fires when nothing has already set it —
    i.e. on the SQLite engine the test suite runs against, where the column
    has no real server-side default (see the field comment above).

    Not a per-flush `MAX(seq)+1` read: SQLAlchemy fires every pending
    `before_insert` for a flush *before* issuing any of their INSERTs, so two
    `AuditLog` rows added in the same flush would both read the same MAX and
    collide on the unique constraint — caught, not corrupted, but still wrong
    for what should be an ordinary write. Instead this keeps a running counter
    on the DBAPI connection itself (`connection.info`, which SQLAlchemy keeps
    alive across checkouts of the same pooled connection): the *first* call on
    a given connection reads the real current max once; every call after that
    only increments in Python, so no two rows in the same flush — or the same
    connection's lifetime — can land on the same value. This is intentionally
    scoped to a single connection and is not a substitute for PostgreSQL's
    real sequence under multiple concurrent connections; it only ever runs
    against the single-connection SQLite engine the test suite uses.
    """
    if connection.dialect.name != "sqlite" or target.seq is not None:
        return
    if _SQLITE_SEQ_COUNTER_KEY not in connection.info:
        current_max = connection.execute(
            select(func.max(AuditLog.__table__.c.seq))
        ).scalar()
        connection.info[_SQLITE_SEQ_COUNTER_KEY] = current_max or 0
    connection.info[_SQLITE_SEQ_COUNTER_KEY] += 1
    target.seq = connection.info[_SQLITE_SEQ_COUNTER_KEY]
