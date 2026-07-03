"""drop vestigial categorization columns off erp_entries

Revision ID: 0011_drop_entry_categorization
Revises: 0010_ai_categorization_store
Create Date: 2026-07-03

``ErpEntry`` rows are raw financial context and are never categorized, yet the
table carried an unused categorization/ground-truth block mirroring the old
``InvoiceLine`` shape. Those columns were always NULL. Drop them; AI output only
ever exists for invoice lines and now lives in the ai_api-owned store. Reversible:
downgrade re-adds the nullable columns.

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_drop_entry_categorization"
down_revision = "0010_ai_categorization_store"
branch_labels = None
depends_on = None

_DROPPED = [
    "level_1", "level_2", "level_3", "account_code", "account_name",
    "confidence", "rationale",
    "gt_level_1", "gt_level_2", "gt_level_3", "gt_account_code",
]


def upgrade() -> None:
    for col in _DROPPED:
        op.drop_column("erp_entries", col)


def downgrade() -> None:
    op.add_column("erp_entries", sa.Column("gt_account_code", sa.String(), nullable=True))
    op.add_column("erp_entries", sa.Column("gt_level_3", sa.String(), nullable=True))
    op.add_column("erp_entries", sa.Column("gt_level_2", sa.String(), nullable=True))
    op.add_column("erp_entries", sa.Column("gt_level_1", sa.String(), nullable=True))
    op.add_column("erp_entries", sa.Column("rationale", sa.String(), nullable=True))
    op.add_column("erp_entries", sa.Column("confidence", sa.Numeric(4, 3), nullable=True))
    op.add_column("erp_entries", sa.Column("account_name", sa.String(), nullable=True))
    op.add_column("erp_entries", sa.Column("account_code", sa.String(), nullable=True))
    op.add_column("erp_entries", sa.Column("level_3", sa.String(), nullable=True))
    op.add_column("erp_entries", sa.Column("level_2", sa.String(), nullable=True))
    op.add_column("erp_entries", sa.Column("level_1", sa.String(), nullable=True))
