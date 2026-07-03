"""erp entries: invoices.file_id + erp_entries.voucher_id

Revision ID: 0004_entries_voucher_file
Revises: 0003_clerk_org_sync
Create Date: 2026-07-02

Entry-first ERP ingestion: the invoice scan gains a reference into the internal
File domain (``invoices.file_id``), and the raw GL entry gains the ERP voucher it
was posted under (``erp_entries.voucher_id``). The voucher lives on the entry, not
on the invoice. Both columns are additive and nullable, so backfill-safe.

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_entries_voucher_file"
down_revision = "0003_clerk_org_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("file_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_invoices_file_id_files",
        "invoices",
        "files",
        ["file_id"],
        ["id"],
    )
    op.add_column("erp_entries", sa.Column("voucher_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("erp_entries", "voucher_id")
    op.drop_constraint("fk_invoices_file_id_files", "invoices", type_="foreignkey")
    op.drop_column("invoices", "file_id")
