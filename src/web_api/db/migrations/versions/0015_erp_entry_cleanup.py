"""ErpEntry: rename entry_date->accounting_date; drop erp_integration_id

Revision ID: 0015_erp_entry_cleanup
Revises: 0014_drop_spendcat_account
Create Date: 2026-07-04

The single ``entry_date`` is renamed to ``accounting_date`` (the ledger posting
date, and the axis for period reporting) — data preserving. The redundant
``erp_integration_id`` is dropped: an entry's integration is reached through its
account (``erp_account_id → ErpAccount.erp_integration_id``). Reversible:
downgrade re-adds a nullable ``erp_integration_id`` (+FK) and renames the date
back; historical integration values are not reconstructed.

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015_erp_entry_cleanup"
down_revision = "0014_drop_spendcat_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("erp_entries", "entry_date", new_column_name="accounting_date")
    op.drop_column("erp_entries", "erp_integration_id")


def downgrade() -> None:
    op.add_column(
        "erp_entries", sa.Column("erp_integration_id", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        "erp_entries_erp_integration_id_fkey", "erp_entries", "erp_integrations",
        ["erp_integration_id"], ["id"],
    )
    op.alter_column("erp_entries", "accounting_date", new_column_name="entry_date")
