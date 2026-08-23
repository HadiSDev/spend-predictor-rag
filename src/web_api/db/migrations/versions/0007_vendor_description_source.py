"""Record who wrote a vendor's description.

The supplier catalog is global, so an enrichment run writes rows every tenant
reads. Without a provenance column there is no way to tell a description a person
corrected from one a model guessed, and the next run would overwrite the
correction for everybody with no trace that it had been made.

Existing descriptions are stamped ``human``: nothing has ever written this column
automatically, so anything already there was typed or came from an ERP's own
master data — either way, not something an enrichment run may replace.

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
