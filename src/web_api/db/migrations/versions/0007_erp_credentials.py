"""erp_credentials: encrypted integration connection config

Revision ID: 0007_erp_credentials
Revises: 0006_erp_account_sync_vat
Create Date: 2026-07-02

Adds the ``erp_credentials`` table holding an ErpIntegration's connection config
encrypted at rest (one active credential per integration). Additive; revision id
kept <=32 chars for ``alembic_version``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_erp_credentials"
down_revision = "0006_erp_account_sync_vat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_credentials",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("erp_integration_id", sa.String(), nullable=False),
        sa.Column("encrypted_config", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["erp_integration_id"], ["erp_integrations.id"]),
        sa.UniqueConstraint("erp_integration_id", name="uq_erp_credentials_integration"),
    )


def downgrade() -> None:
    op.drop_table("erp_credentials")
