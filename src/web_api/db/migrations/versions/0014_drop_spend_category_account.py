"""drop account_code/account_name off spend_categories

Revision ID: 0014_drop_spendcat_account
Revises: 0013_global_vendor_catalog
Create Date: 2026-07-03

A ``SpendCategory`` is a node in the company's own spend taxonomy, identified by
its level hierarchy — not by an ERP account code/name (those belong to
``ErpAccount``). Drop the vestigial ``account_code``/``account_name`` columns.
The categorizer now resolves a line to a spend node by its ``(level_2, level_3)``
path. Reversible: downgrade re-adds the columns (nullable, since existing rows
have no value to backfill).

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014_drop_spendcat_account"
down_revision = "0013_global_vendor_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("spend_categories", "account_name")
    op.drop_column("spend_categories", "account_code")


def downgrade() -> None:
    op.add_column("spend_categories", sa.Column("account_code", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("account_name", sa.String(), nullable=True))
