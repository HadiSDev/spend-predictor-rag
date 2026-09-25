"""Invoice-scoped supplier overrides, and the record of what a human verified

Revision ID: 0005_invoice_corrections
Revises: 0004_org_spend_trees
Create Date: 2026-08-10

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0005_invoice_corrections'
down_revision = '0004_org_spend_trees'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('supplier_name', sa.String(), nullable=True))
    op.add_column(
        'invoices', sa.Column('supplier_country_code', sa.String(length=2), nullable=True)
    )
    op.add_column('invoices', sa.Column('supplier_vat_number', sa.String(), nullable=True))
    op.add_column(
        'invoices',
        sa.Column(
            'verified_fields', sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    op.add_column(
        'invoices', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column('invoices', sa.Column('verified_by', sa.String(), nullable=True))
    op.add_column(
        'invoice_lines',
        sa.Column(
            'verified_fields', sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
    )


def downgrade() -> None:
    op.drop_column('invoice_lines', 'verified_fields')
    op.drop_column('invoices', 'verified_by')
    op.drop_column('invoices', 'verified_at')
    op.drop_column('invoices', 'verified_fields')
    op.drop_column('invoices', 'supplier_vat_number')
    op.drop_column('invoices', 'supplier_country_code')
    op.drop_column('invoices', 'supplier_name')
