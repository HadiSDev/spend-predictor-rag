"""ai_api categorization store; drop AI columns off invoice_lines

Revision ID: 0010_ai_categorization_store
Revises: 0009_line_spend_category
Create Date: 2026-07-03

AI-produced categorization output moves off the domain ``invoice_lines`` table
into the ai_api-owned ``line_categorizations`` store (keyed by invoice line id).
The domain line keeps only ``spend_category_id`` (the accepted assignment) and
loses the predicted level snapshot, confidence/rationale, ground truth, and the
ERP line id. Reversible: downgrade re-adds the columns and drops the store.

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_ai_categorization_store"
down_revision = "0009_line_spend_category"
branch_labels = None
depends_on = None

_DROPPED_LINE_COLUMNS = [
    "level_1", "level_2", "level_3", "account_code", "account_name",
    "confidence", "rationale",
    "gt_level_1", "gt_level_2", "gt_level_3", "gt_account_code",
    "line_erp_id",
]


def upgrade() -> None:
    op.create_table(
        "line_categorizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("invoice_line_id", sa.String(), nullable=False),
        sa.Column("spend_category_id", sa.String(), nullable=True),
        sa.Column("level_1", sa.String(), nullable=True),
        sa.Column("level_2", sa.String(), nullable=True),
        sa.Column("level_3", sa.String(), nullable=True),
        sa.Column("account_code", sa.String(), nullable=True),
        sa.Column("account_name", sa.String(), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("gt_level_1", sa.String(), nullable=True),
        sa.Column("gt_level_2", sa.String(), nullable=True),
        sa.Column("gt_level_3", sa.String(), nullable=True),
        sa.Column("gt_account_code", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["invoice_line_id"], ["invoice_lines.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spend_category_id"], ["spend_categories.id"]),
        sa.UniqueConstraint("invoice_line_id"),
    )

    for col in _DROPPED_LINE_COLUMNS:
        op.drop_column("invoice_lines", col)


def downgrade() -> None:
    op.add_column("invoice_lines", sa.Column("line_erp_id", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("gt_account_code", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("gt_level_3", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("gt_level_2", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("gt_level_1", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("rationale", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("confidence", sa.Numeric(4, 3), nullable=True))
    op.add_column("invoice_lines", sa.Column("account_name", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("account_code", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("level_3", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("level_2", sa.String(), nullable=True))
    op.add_column("invoice_lines", sa.Column("level_1", sa.String(), nullable=True))

    op.drop_table("line_categorizations")
