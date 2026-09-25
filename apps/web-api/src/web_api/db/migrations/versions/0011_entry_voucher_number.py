"""A posting carries the ERP's own voucher number beside its voucher id

Revision ID: 0011_entry_voucher_number
Revises: 0010_document_totals
Create Date: 2026-09-26

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0011_entry_voucher_number'
down_revision = '0010_document_totals'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('erp_entries', sa.Column('voucher_number', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('erp_entries', 'voucher_number')
