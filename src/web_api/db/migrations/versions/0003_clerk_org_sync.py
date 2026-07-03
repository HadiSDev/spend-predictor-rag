"""clerk org sync: webhook_events + organization.suspended_at

Revision ID: 0003_clerk_org_sync
Revises: 0002_org_company_management
Create Date: 2026-07-02

Adds the WebhookEvent idempotency/audit table and Organization.suspended_at for
the clerk-org-sync change. Additive and backfill-safe.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_clerk_org_sync"
down_revision = "0002_org_company_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_webhook_events_event_id", "webhook_events", ["event_id"])


def downgrade() -> None:
    op.drop_constraint("uq_webhook_events_event_id", "webhook_events", type_="unique")
    op.drop_table("webhook_events")
    op.drop_column("organizations", "suspended_at")
