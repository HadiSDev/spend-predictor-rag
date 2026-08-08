"""Record where an invoice's values came from

Revision ID: 0018_invoice_source
Revises: 0017_entry_source_line
Create Date: 2026-08-08

Adds ``invoices.source`` — 'erp' or 'pdf_extraction'.

Corrections apply only to what the AI produced. Without a provenance marker that
rule is a convention the UI remembers; with one it is a condition the API can
enforce, which is what keeps the as-posted ERP columns evidence.

Existing rows are all sync-created, so they backfill to 'erp'. Reversible:
downgrade drops the column.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0018_invoice_source"
down_revision = "0017_entry_source_line"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("source", sa.String(), nullable=False, server_default="erp"),
    )


def downgrade() -> None:
    op.drop_column("invoices", "source")
