"""Line unit of measure, and the invoice number printed on the document

Revision ID: 0003_line_unit_and_doc_number
Revises: 0002_line_origin_and_doc_status
Create Date: 2026-08-09

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0003_line_unit_and_doc_number'
down_revision = '0002_line_origin_and_doc_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('invoice_lines', sa.Column('unit', sa.String(), nullable=True))
    op.add_column(
        'invoices', sa.Column('document_invoice_number', sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('invoices', 'document_invoice_number')
    op.drop_column('invoice_lines', 'unit')
