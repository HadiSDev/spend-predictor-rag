"""Line provenance and invoice document-processing state

Revision ID: 0002_line_origin_and_doc_status
Revises: 0001_baseline_schema
Create Date: 2026-08-09

Adds the two columns that make the invoice **line** the unit of spend:

- ``invoice_lines.origin`` — which source produced the line (``erp`` /
  ``document_ai`` / ``entry_fallback``). Stored, never inferred: a stand-in line
  and an extracted line can be identical in every other field.
- ``invoices.doc_status`` (+ ``doc_attempts`` / ``doc_error`` /
  ``doc_processed_at``) — whether the attached scan has been turned into lines.
  Distinct from ``invoices.status``, which stays the categorization rollup.

**The backfill queues the existing corpus.** Every line written before this
revision came from the ERP, so it becomes ``erp``. Every invoice that already
carries a ``file_id`` becomes ``pending``, so the first run of
``python -m ai_api.documents.runner`` drains the backlog with no separate step;
the rest become ``not_applicable``, which is the ordinary state for a voucher
with no scan and is not a failure.

Downgrade drops the columns. Lines that extraction has already replaced are
**not** restored by it — the pre-extraction lines are gone, and only their audit
rows remain. That is why this revision is deployed ahead of the extraction stage.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0002_line_origin_and_doc_status'
down_revision = '0001_baseline_schema'
branch_labels = None
depends_on = None

# The stage's discovery query is `doc_status = 'pending' ORDER BY invoice_date`,
# so the index carries both columns in that order.
_IX_DOC_STATUS = "ix_invoices_doc_status_invoice_date"
# Replacement and stand-in materialization both ask for one invoice's lines of a
# given origin.
_IX_LINE_ORIGIN = "ix_invoice_lines_invoice_id_origin"


def upgrade() -> None:
    # server_default carries the backfill for existing rows; the column is
    # NOT NULL from the start because there is no such thing as a line with no
    # source. It stays on the column so a writer that omits origin — an older
    # deploy mid-rollout — still lands a valid row.
    op.add_column(
        'invoice_lines',
        sa.Column('origin', sa.String(), nullable=False, server_default='erp'),
    )
    # Position on the invoice. Existing rows all take 0, which leaves their
    # relative order to the `id` tiebreak — exactly what it was before. New
    # writers set it, so lines land in the order their source stated them.
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

    # Queue every invoice that already has a scan. `not_applicable` is already in
    # place from the server_default, so only the documented ones are touched.
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
