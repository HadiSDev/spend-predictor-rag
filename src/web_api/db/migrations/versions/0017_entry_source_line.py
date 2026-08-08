"""Link a GL posting to the invoice line it came from

Revision ID: 0017_entry_source_line
Revises: 0016_base_currency
Create Date: 2026-08-08

Adds ``erp_entries.source_invoice_line_id`` — a nullable FK to
``invoice_lines``.

**One invoice line has many entries.** A line can be posted across several
accounts, so the link points from the posting to the line, never the other way.
It is nullable because most postings are not line-derived at all: input VAT, the
accounts-payable counterparty, and any journal entry have no line behind them.

The entry itself gains no categorization. Spend categories live on the invoice
line; this column is only what lets a posting be read against the line whose
category applies to it.

Reversible: downgrade drops the column. Nothing is backfilled — the source line
is data only the connector can supply, so existing rows stay null until they are
re-synced.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017_entry_source_line"
down_revision = "0016_base_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "erp_entries",
        sa.Column("source_invoice_line_id", sa.String(), nullable=True),
    )
    # Named explicitly so the downgrade can drop it on backends that require a
    # constraint name (SQLite renders it inline; PostgreSQL needs the name).
    op.create_foreign_key(
        "fk_erp_entries_source_invoice_line_id",
        "erp_entries",
        "invoice_lines",
        ["source_invoice_line_id"],
        ["id"],
    )
    # Every read of a line's postings filters on this column.
    op.create_index(
        "ix_erp_entries_source_invoice_line_id",
        "erp_entries",
        ["source_invoice_line_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_erp_entries_source_invoice_line_id", table_name="erp_entries")
    op.drop_constraint(
        "fk_erp_entries_source_invoice_line_id", "erp_entries", type_="foreignkey"
    )
    op.drop_column("erp_entries", "source_invoice_line_id")
