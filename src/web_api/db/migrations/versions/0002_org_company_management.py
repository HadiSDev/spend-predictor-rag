"""org/company management fields

Revision ID: 0002_org_company_management
Revises: 0001_add_clerk_external_ids
Create Date: 2026-07-02

Adds Organization profile/lifecycle (slug, status), Company soft-deactivation
(is_active, deactivated_at), and platform role (User.is_system_admin) for the
org-company-management change. All additive and backfill-safe.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_org_company_management"
down_revision = "0001_add_clerk_external_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Organizations
    op.add_column("organizations", sa.Column("slug", sa.String(), nullable=True))
    op.create_unique_constraint("uq_organizations_slug", "organizations", ["slug"])
    op.add_column(
        "organizations",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    # Companies
    op.add_column(
        "companies",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "companies",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Users
    op.add_column(
        "users",
        sa.Column("is_system_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_system_admin")
    op.drop_column("companies", "deactivated_at")
    op.drop_column("companies", "is_active")
    op.drop_column("organizations", "status")
    op.drop_constraint("uq_organizations_slug", "organizations", type_="unique")
    op.drop_column("organizations", "slug")
