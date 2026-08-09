"""Insertion-order sequence for the audit trail

Revision ID: 0019_audit_log_seq
Revises: 0018_invoice_source
Create Date: 2026-08-09

Adds ``audit_log.seq`` — a monotonic surrogate for "the order these rows were
written," independent of ``created_at`` (constant for the whole duration of a
PostgreSQL transaction, so rows written together always tie) and independent
of ``id`` (a random UUID with no relation to write order at all). The
voucher-wide audit feed (``GET /erp-entries/vouchers/{id}/audit``) orders by
this column, newest first.

A real PostgreSQL sequence backs it (``nextval`` as the column default) —
atomic, so it stays correct under concurrent writers on multiple app
instances, which a Python-computed timestamp or counter is not.

**This migration targets PostgreSQL only** — the only backend Alembic runs
against in this project (``env.py`` reads ``DATABASE_URL``, which is always a
``postgresql://`` URL here; see ``.env``/``.env.example``). The test suite
never runs this migration: it builds its schema via
``SQLModel.metadata.create_all()`` directly against an in-memory SQLite
engine, where the ORM model (``db/models/audit_log.py``) supplies its own,
separate fallback for populating ``seq`` — see that file's comments. This file
makes no attempt to also run correctly against SQLite (an earlier version of
it pretended to and didn't; asserting the dialect below fails loudly instead
of silently doing the wrong thing).

Existing rows have no recorded insertion order — nothing captured it before
now — so they are backfilled deterministically by the best available proxy:
``created_at`` ascending, ``id`` ascending as the tiebreak for rows sharing a
timestamp. That is the same ordering the per-line audit endpoint
(``GET /invoice-lines/{id}/audit``) already uses, so the backfilled order
matches what that endpoint has always shown for these same rows.

Reversible: downgrade drops the sequence, its default, and the column.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019_audit_log_seq"
down_revision = "0018_invoice_source"
branch_labels = None
depends_on = None

_SEQUENCE = "audit_log_seq_seq"
_UNIQUE = "uq_audit_log_seq"


def _require_postgresql() -> None:
    dialect = op.get_bind().dialect.name
    if dialect != "postgresql":
        raise RuntimeError(
            f"0019_audit_log_seq targets PostgreSQL only, got {dialect!r}. "
            "See the module docstring."
        )


def upgrade() -> None:
    _require_postgresql()
    op.add_column("audit_log", sa.Column("seq", sa.BigInteger(), nullable=True))

    # Backfill by the best available proxy for insertion order (see module
    # docstring): created_at, then id to break a tie.
    op.execute(
        """
        UPDATE audit_log
        SET seq = ranked.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
            FROM audit_log
        ) AS ranked
        WHERE audit_log.id = ranked.id
        """
    )
    op.execute(f"CREATE SEQUENCE {_SEQUENCE} OWNED BY audit_log.seq")
    # Start the sequence just past the highest backfilled value (1 on an
    # empty table) so the first row written after this migration can never
    # collide with a backfilled one.
    op.execute(
        f"SELECT setval('{_SEQUENCE}', "
        f"COALESCE((SELECT MAX(seq) FROM audit_log), 0) + 1, false)"
    )
    op.execute(
        f"ALTER TABLE audit_log ALTER COLUMN seq SET DEFAULT nextval('{_SEQUENCE}')"
    )

    op.alter_column("audit_log", "seq", nullable=False)
    op.create_unique_constraint(_UNIQUE, "audit_log", ["seq"])


def downgrade() -> None:
    _require_postgresql()
    op.drop_constraint(_UNIQUE, "audit_log", type_="unique")
    op.execute("ALTER TABLE audit_log ALTER COLUMN seq DROP DEFAULT")
    op.execute(f"DROP SEQUENCE IF EXISTS {_SEQUENCE}")
    op.drop_column("audit_log", "seq")
