"""Store what the document said about its own arithmetic.

Revision ID: 0010_document_totals
Revises: 0009_categorization_cache

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_document_totals"
down_revision = "0009_categorization_cache"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("invoices", "document_total", sa.Numeric(14, 2)),
    ("invoices", "document_tax", sa.Numeric(14, 2)),
    ("invoices", "document_subtotal", sa.Numeric(14, 2)),
    ("invoice_lines", "subtotal", sa.Numeric(14, 2)),
    ("invoice_lines", "tax_amount", sa.Numeric(14, 2)),
    ("invoice_lines", "tax_rate", sa.Numeric(7, 3)),
    ("invoice_lines", "discount", sa.Numeric(14, 2)),
)


def upgrade() -> None:
    for table, column, type_ in _COLUMNS:
        op.add_column(table, sa.Column(column, type_, nullable=True))


def downgrade() -> None:
    for table, column, _ in reversed(_COLUMNS):
        op.drop_column(table, column)
