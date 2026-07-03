"""erp_accounts: sync_enabled + with_vat

Revision ID: 0006_erp_account_sync_vat
Revises: 0005_spend_category_levels
Create Date: 2026-07-02

Adds our-side account selection (``sync_enabled``, gates entry fetch) and the ERP
VAT characteristic (``with_vat``) to ``erp_accounts``. Both additive with server
defaults so existing rows backfill safely (all enabled, no VAT assumed). Revision
id kept <=32 chars for ``alembic_version``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_erp_account_sync_vat"
down_revision = "0005_spend_category_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "erp_accounts",
        sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "erp_accounts",
        sa.Column("with_vat", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("erp_accounts", "with_vat")
    op.drop_column("erp_accounts", "sync_enabled")
