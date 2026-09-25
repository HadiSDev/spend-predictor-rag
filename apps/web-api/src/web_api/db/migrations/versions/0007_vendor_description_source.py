"""Record who wrote a vendor's description.

Revision ID: 0007_vendor_description_source
Revises: 0006_line_item_name

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_vendor_description_source"
down_revision = "0006_line_item_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vendors", sa.Column("description_source", sa.String(), nullable=True)
    )
    op.execute(
        "UPDATE vendors SET description_source = 'human' "
        "WHERE description IS NOT NULL AND TRIM(description) <> ''"
    )


def downgrade() -> None:
    op.drop_column("vendors", "description_source")
