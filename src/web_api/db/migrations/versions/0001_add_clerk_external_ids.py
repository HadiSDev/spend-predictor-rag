"""add clerk external identity ids to organizations and users

Revision ID: 0001_add_clerk_external_ids
Revises:
Create Date: 2026-07-01

Adds nullable, unique external-identity columns so app records can be linked to
Clerk principals (see change: web-api-clerk-review). NULL for synthetic tenants.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_add_clerk_external_ids"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("clerk_org_id", sa.String(), nullable=True))
    op.create_unique_constraint("uq_organizations_clerk_org_id", "organizations", ["clerk_org_id"])
    op.add_column("users", sa.Column("clerk_user_id", sa.String(), nullable=True))
    op.create_unique_constraint("uq_users_clerk_user_id", "users", ["clerk_user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_clerk_user_id", "users", type_="unique")
    op.drop_column("users", "clerk_user_id")
    op.drop_constraint("uq_organizations_clerk_org_id", "organizations", type_="unique")
    op.drop_column("organizations", "clerk_org_id")
