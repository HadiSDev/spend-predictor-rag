"""global supplier catalog: reshape vendors; drop invoice_lines.vendor_id

Revision ID: 0013_global_vendor_catalog
Revises: 0012_categorization_on_line
Create Date: 2026-07-03

``Vendor`` becomes a global supplier database rather than company-scoped ERP
master data: it drops ``company_id`` (and its FK), ``erp_id`` and ``raw_json``,
and gains a free-text ``description``. Identity is now VAT-else-name, resolved by
the sync runner. Invoice lines no longer reference a vendor (``vendor_id``
dropped); only ``Invoice.vendor_id`` remains. Reversible: downgrade restores the
old columns (company scope re-added nullable, since it was populated from a live
sync).

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_global_vendor_catalog"
down_revision = "0012_categorization_on_line"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Invoice lines no longer point at a vendor.
    op.drop_column("invoice_lines", "vendor_id")

    # Vendors become a global, non-ERP-specific supplier catalog.
    op.add_column("vendors", sa.Column("description", sa.String(), nullable=True))
    op.drop_column("vendors", "raw_json")
    op.drop_column("vendors", "erp_id")
    op.drop_column("vendors", "company_id")


def downgrade() -> None:
    op.add_column("vendors", sa.Column("company_id", sa.String(), nullable=True))
    op.add_column("vendors", sa.Column("erp_id", sa.String(), nullable=True))
    op.add_column("vendors", sa.Column("raw_json", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "vendors_company_id_fkey", "vendors", "companies", ["company_id"], ["id"]
    )
    op.drop_column("vendors", "description")

    op.add_column("invoice_lines", sa.Column("vendor_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "invoice_lines_vendor_id_fkey", "invoice_lines", "vendors", ["vendor_id"], ["id"]
    )
