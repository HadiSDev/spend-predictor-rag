"""invoice_lines.spend_category_id: FK to the company spend tree

Revision ID: 0009_line_spend_category
Revises: 0008_drop_invoice_erp_link
Create Date: 2026-07-03

Give each invoice line a normalized link to its assigned ``SpendCategory``. The
existing level_*/account_* result columns remain a denormalized snapshot of the
category at categorization time; this FK is the relation. Additive and nullable
(populated later by the categorizer), so backfill-safe.

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_line_spend_category"
down_revision = "0008_drop_invoice_erp_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoice_lines", sa.Column("spend_category_id", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        "invoice_lines_spend_category_id_fkey",
        "invoice_lines",
        "spend_categories",
        ["spend_category_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "invoice_lines_spend_category_id_fkey", "invoice_lines", type_="foreignkey"
    )
    op.drop_column("invoice_lines", "spend_category_id")
