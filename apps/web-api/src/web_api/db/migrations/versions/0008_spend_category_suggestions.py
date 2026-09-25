"""Categories a company's tree is missing, proposed with their evidence.

Revision ID: 0008_spend_category_suggestions
Revises: 0007_vendor_description_source

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_spend_category_suggestions"
down_revision = "0007_vendor_description_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spend_category_suggestions",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("spend_tree_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("parent_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("evidence_line_ids", sa.JSON(), nullable=True),
        sa.Column("state", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_category_id", sa.String(), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["spend_tree_id"], ["spend_trees.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["spend_categories.id"]),
        sa.ForeignKeyConstraint(["created_category_id"], ["spend_categories.id"]),
    )
    op.create_index(
        "ix_spend_category_suggestions_tree_state",
        "spend_category_suggestions",
        ["spend_tree_id", "state"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_spend_category_suggestions_tree_state",
        table_name="spend_category_suggestions",
    )
    op.drop_table("spend_category_suggestions")
