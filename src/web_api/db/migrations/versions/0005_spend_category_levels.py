"""rename Account->SpendCategory and level columns to level_N

Revision ID: 0005_spend_category_levels
Revises: 0004_entries_voucher_file
Create Date: 2026-07-02

Renames the spend-tree table ``accounts`` -> ``spend_categories`` and adopts the
``level_1``..``level_4`` naming across the spend-tree node and the applied
categorization result columns (``invoice_lines``, ``erp_entries``,
``recommendations``). ``level_1`` (Direct/Indirect) and ``level_4`` are added to
the spend category node. Revision id kept <=32 chars for ``alembic_version``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_spend_category_levels"
down_revision = "0004_entries_voucher_file"
branch_labels = None
depends_on = None

# (table, [(old, new), ...]) for the level result columns
_RESULT_RENAMES = {
    "invoice_lines": [
        ("level1", "level_1"), ("level2", "level_2"), ("level3", "level_3"),
        ("gt_level1", "gt_level_1"), ("gt_level2", "gt_level_2"), ("gt_level3", "gt_level_3"),
    ],
    "erp_entries": [
        ("level1", "level_1"), ("level2", "level_2"), ("level3", "level_3"),
        ("gt_level1", "gt_level_1"), ("gt_level2", "gt_level_2"), ("gt_level3", "gt_level_3"),
    ],
    "recommendations": [
        ("category_level2", "category_level_2"), ("category_level3", "category_level_3"),
    ],
}


def upgrade() -> None:
    # Spend-tree node: rename table + level columns, add level_1 / level_4.
    op.rename_table("accounts", "spend_categories")
    op.alter_column("spend_categories", "level2", new_column_name="level_2")
    op.alter_column("spend_categories", "level3", new_column_name="level_3")
    op.add_column("spend_categories", sa.Column("level_1", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("level_4", sa.String(), nullable=True))

    # Applied result columns.
    for table, renames in _RESULT_RENAMES.items():
        for old, new in renames:
            op.alter_column(table, old, new_column_name=new)


def downgrade() -> None:
    for table, renames in _RESULT_RENAMES.items():
        for old, new in renames:
            op.alter_column(table, new, new_column_name=old)

    op.drop_column("spend_categories", "level_4")
    op.drop_column("spend_categories", "level_1")
    op.alter_column("spend_categories", "level_3", new_column_name="level3")
    op.alter_column("spend_categories", "level_2", new_column_name="level2")
    op.rename_table("spend_categories", "accounts")
