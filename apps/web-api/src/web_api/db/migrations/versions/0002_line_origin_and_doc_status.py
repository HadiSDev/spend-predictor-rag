"""Line provenance and invoice document-processing state

Revision ID: 0002_line_origin_and_doc_status
Revises: 0001_baseline_schema
Create Date: 2026-08-09

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0002_line_origin_and_doc_status'
down_revision = '0001_baseline_schema'
branch_labels = None
depends_on = None

_IX_DOC_STATUS = "ix_invoices_doc_status_invoice_date"
_IX_LINE_ORIGIN = "ix_invoice_lines_invoice_id_origin"


def upgrade() -> None:
    op.add_column(
        'invoice_lines',
        sa.Column('origin', sa.String(), nullable=False, server_default='erp'),
    )
    op.add_column(
        'invoice_lines',
        sa.Column('sequence', sa.Integer(), nullable=False, server_default='0'),
    )

    op.add_column(
        'invoices',
        sa.Column(
            'doc_status', sa.String(), nullable=False, server_default='not_applicable'
        ),
    )
    op.add_column(
        'invoices',
        sa.Column('doc_attempts', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column('invoices', sa.Column('doc_error', sa.String(), nullable=True))
    op.add_column(
        'invoices',
        sa.Column('doc_processed_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        "UPDATE invoices SET doc_status = 'pending' WHERE file_id IS NOT NULL"
    )

    op.create_index(
        _IX_DOC_STATUS, 'invoices', ['doc_status', 'invoice_date'], unique=False
    )
    op.create_index(
        _IX_LINE_ORIGIN, 'invoice_lines', ['invoice_id', 'origin'], unique=False
    )


def downgrade() -> None:
    op.drop_index(_IX_LINE_ORIGIN, table_name='invoice_lines')
    op.drop_index(_IX_DOC_STATUS, table_name='invoices')

    op.drop_column('invoices', 'doc_processed_at')
    op.drop_column('invoices', 'doc_error')
    op.drop_column('invoices', 'doc_attempts')
    op.drop_column('invoices', 'doc_status')
    op.drop_column('invoice_lines', 'sequence')
    op.drop_column('invoice_lines', 'origin')
