"""Line unit of measure, and the invoice number printed on the document

Revision ID: 0003_line_unit_and_doc_number
Revises: 0002_line_origin_and_doc_status
Create Date: 2026-08-09

Two nullable columns, both filled only by what a source actually stated:

- ``invoice_lines.unit`` — what the line's ``quantity`` counts. A bare quantity
  is ambiguous (``12`` against "Consulting" is twelve hours or twelve days), and
  unit prices cannot be compared across suppliers without it. Null for every
  existing row and for most new ones: an ERP bill line states an account and an
  amount, not a unit of measure.
- ``invoices.document_invoice_number`` — the supplier's number as read off the
  scan, **beside** the as-posted ``invoice_number``, which extraction never
  rewrites. The as-posted value is frequently not an invoice number at all:
  Billy's ``suppliersInvoiceNo`` is user-entered and often null and ``voucherNo``
  is blank at least as often, so the connector falls back to the bill id.

No backfill: neither value can be derived from what is already stored. Filling
them would mean guessing, and a guessed invoice number is worse than none —
someone would reconcile against it.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# Kept under 32 characters: `alembic_version.version_num` is varchar(32), so a
# longer id fails the upgrade at the very last statement, after all its DDL has
# run. apps/web-api/tests/test_migrations.py is what catches that.
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
