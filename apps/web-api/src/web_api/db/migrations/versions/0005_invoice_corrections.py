"""Invoice-scoped supplier overrides, and the record of what a human verified

Revision ID: 0005_invoice_corrections
Revises: 0004_org_spend_trees
Create Date: 2026-08-10

Seven columns, all additive, none rewritten:

- ``invoices.supplier_name`` / ``supplier_country_code`` / ``supplier_vat_number``
  — a human's correction of the supplier **for this invoice alone**. `Vendor` is
  a global catalog shared across organizations, so a correction written through
  to the vendor row would rewrite the supplier for every other tenant. Null
  means "no correction — use the linked vendor", which is every existing row.
- ``invoices.verified_fields`` / ``invoice_lines.verified_fields`` — the names of
  the fields a human has settled. Defaults to ``'[]'`` server-side, so every
  existing row reads as unverified with no backfill, and NOT NULL because
  "nothing settled" is a fact rather than an unknown.
- ``invoices.verified_at`` / ``verified_by`` — when, and by whom. ``verified_by``
  holds a user id and never ``system``: an automated write is not a verification.

Nothing is dropped and no data is rewritten, so this is reversible and safe to
deploy ahead of the API that reads it. Until the first verification lands, the
sync behaves exactly as it does today.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# Kept under 32 characters: `alembic_version.version_num` is varchar(32), so a
# longer id fails the upgrade at the very last statement, after all its DDL has
# run. apps/web-api/tests/test_migrations.py is what catches that.
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
    # server_default rather than a Python-side default: existing rows are filled
    # by the ALTER itself, so no backfill statement is needed and no row is ever
    # left with a NULL the model promises cannot happen.
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
