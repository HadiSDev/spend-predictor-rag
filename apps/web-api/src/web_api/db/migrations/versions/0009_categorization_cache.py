"""Remember what the categorizer already answered.

Most lines on a real ledger are repeats — the same monthly ticket from the same
supplier — and each one is a model call of several seconds.

The unique key is `(question_key, tree_hash)`, and the tree hash is the
load-bearing half: a cached answer is a pointer into a taxonomy, and a customer
who renames or removes a node has changed what it means. Without the hash the
cache would keep serving answers against a tree that no longer exists, with
nothing to notice it by.

Owned by `ai_api` but migrated here, because this is where the migration chain
lives and a table that exists only via `create_all()` is a table that has never
been proven to build from empty — which is what the squashed baseline exists to
stop happening again.

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
    # No foreign key on `spend_category_id`, deliberately. Every other FK in this
    # schema is NO ACTION, so one here would make deleting a spend category fail
    # on a *cache* row — a customer's tree edit refused by an optimization. A
    # dangling pointer is instead resolved on read: the entry is dropped.


def downgrade() -> None:
    op.drop_index("ix_categorization_cache_question_key", table_name="categorization_cache")
    op.drop_table("categorization_cache")
