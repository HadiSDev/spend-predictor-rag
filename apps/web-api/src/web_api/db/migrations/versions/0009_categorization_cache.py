"""Remember what the categorizer already answered.

Revision ID: 0009_categorization_cache
Revises: 0008_spend_category_suggestions

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_categorization_cache"
down_revision = "0008_spend_category_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categorization_cache",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("question_key", sa.String(), nullable=False),
        sa.Column("tree_hash", sa.String(), nullable=False),
        sa.Column("spend_category_id", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("question_sample", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "question_key", "tree_hash", name="uq_categorization_cache_question"
        ),
    )
    op.create_index(
        "ix_categorization_cache_question_key", "categorization_cache", ["question_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_categorization_cache_question_key", table_name="categorization_cache")
    op.drop_table("categorization_cache")
