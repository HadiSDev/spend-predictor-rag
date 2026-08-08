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

On PostgreSQL a real sequence backs it (``nextval`` as the column default) —
atomic, so it stays correct under concurrent writers on multiple app
instances, which a Python-computed timestamp or counter is not. SQLite (used
only by the test suite, via ``SQLModel.metadata.create_all``, never through
Alembic) has no equivalent for a secondary autoincrementing column that isn't
the table's sole ``INTEGER PRIMARY KEY``; the ORM model
(``db/models/audit_log.py``) supplies a Python-side fallback there instead, so
this migration's PostgreSQL path is the only one exercised for real.

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


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("seq", sa.BigInteger(), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Backfill by the best available proxy for insertion order (see
        # module docstring): created_at, then id to break a tie.
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
        # empty table) so the first row written after this migration can
        # never collide with a backfilled one.
        op.execute(
            f"SELECT setval('{_SEQUENCE}', "
            f"COALESCE((SELECT MAX(seq) FROM audit_log), 0) + 1, false)"
        )
        op.execute(
            f"ALTER TABLE audit_log ALTER COLUMN seq "
            f"SET DEFAULT nextval('{_SEQUENCE}')"
        )
    else:
        # Defensive only — real deployments run this migration against
        # PostgreSQL exclusively; nothing points Alembic at SQLite. Keeps
        # `alembic upgrade head` from hard-failing if that ever changes. An
        # append-only table's `rowid` order is already its insertion order.
        op.execute(
            "UPDATE audit_log SET seq = "
            "(SELECT COUNT(*) FROM audit_log a2 WHERE a2.rowid <= audit_log.rowid)"
        )

    op.alter_column("audit_log", "seq", nullable=False)
    op.create_unique_constraint(_UNIQUE, "audit_log", ["seq"])


def downgrade() -> None:
    op.drop_constraint(_UNIQUE, "audit_log", type_="unique")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE audit_log ALTER COLUMN seq DROP DEFAULT")
        op.execute(f"DROP SEQUENCE IF EXISTS {_SEQUENCE}")
    op.drop_column("audit_log", "seq")
