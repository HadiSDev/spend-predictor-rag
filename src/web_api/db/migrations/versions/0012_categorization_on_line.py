"""categorization result on invoice_lines; audit_log; line_ground_truth

Revision ID: 0012_categorization_on_line
Revises: 0011_drop_entry_categorization
Create Date: 2026-07-03

The categorization *result* moves back onto the domain ``invoice_lines`` table
(level snapshot, account, confidence, rationale) alongside the accepted
``spend_category_id``, and the line's ``status`` now uses the categorization
lifecycle (``uncategorized`` | ``ai_failed`` | ``ai_categorized`` | ``verified``).
A generic append-only ``audit_log`` records changes to invoices and lines. The
ai_api-owned ``line_categorizations`` store is dropped; only synthetic ground
truth remains, in the new ai_api-owned ``line_ground_truth`` table.

Only synthetic/dev data exists at this point, so no row-level data is migrated
off ``line_categorizations`` — a re-sync repopulates the result on each line.
Reversible: downgrade drops the new columns/tables and re-creates the store.

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_categorization_on_line"
down_revision = "0011_drop_entry_categorization"
branch_labels = None
depends_on = None

_LINE_RESULT_COLUMNS = [
    ("level_1", sa.String()),
    ("level_2", sa.String()),
    ("level_3", sa.String()),
    ("account_code", sa.String()),
    ("account_name", sa.String()),
    ("confidence", sa.Numeric(4, 3)),
    ("rationale", sa.String()),
]


def upgrade() -> None:
    # 1. Categorization result columns on the domain line.
    for name, type_ in _LINE_RESULT_COLUMNS:
        op.add_column("invoice_lines", sa.Column(name, type_, nullable=True))

    # 2. Generic append-only audit log.
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])

    # 3. ai_api-owned synthetic ground-truth store (benchmarking only).
    op.create_table(
        "line_ground_truth",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("invoice_line_id", sa.String(), nullable=False),
        sa.Column("gt_level_1", sa.String(), nullable=True),
        sa.Column("gt_level_2", sa.String(), nullable=True),
        sa.Column("gt_level_3", sa.String(), nullable=True),
        sa.Column("gt_account_code", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["invoice_line_id"], ["invoice_lines.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("invoice_line_id"),
    )

    # 4. Drop the old ai_api categorization store (result now lives on the line).
    op.drop_table("line_categorizations")


def downgrade() -> None:
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

    op.drop_table("line_ground_truth")
    op.drop_index("ix_audit_log_entity_id", table_name="audit_log")
    op.drop_table("audit_log")

    for name, _ in reversed(_LINE_RESULT_COLUMNS):
        op.drop_column("invoice_lines", name)
