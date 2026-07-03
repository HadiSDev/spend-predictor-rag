"""drop invoice/line ERP identity: invoices.erp_id + erp_integration_id links

Revision ID: 0008_drop_invoice_erp_link
Revises: 0007_erp_credentials
Create Date: 2026-07-03

The invoice scan is a purely internal document: it references the File domain and
is tied to ERP entries via the voucher, but carries no ERP identity of its own.
The integration provenance lives on the entries, so ``invoices`` and
``invoice_lines`` no longer link to ``erp_integrations``, and ``invoices`` no
longer stores the ERP scan id (``erp_id``). Reversible: downgrade re-adds the
nullable columns and their foreign keys.

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_drop_invoice_erp_link"
down_revision = "0007_erp_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "invoice_lines_erp_integration_id_fkey", "invoice_lines", type_="foreignkey"
    )
    op.drop_column("invoice_lines", "erp_integration_id")

    op.drop_constraint(
        "invoices_erp_integration_id_fkey", "invoices", type_="foreignkey"
    )
    op.drop_column("invoices", "erp_integration_id")
    op.drop_column("invoices", "erp_id")


def downgrade() -> None:
    op.add_column("invoices", sa.Column("erp_id", sa.String(), nullable=True))
    op.add_column(
        "invoices", sa.Column("erp_integration_id", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        "invoices_erp_integration_id_fkey",
        "invoices",
        "erp_integrations",
        ["erp_integration_id"],
        ["id"],
    )
    op.add_column(
        "invoice_lines", sa.Column("erp_integration_id", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        "invoice_lines_erp_integration_id_fkey",
        "invoice_lines",
        "erp_integrations",
        ["erp_integration_id"],
        ["id"],
    )
