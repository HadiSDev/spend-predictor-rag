"""Where an invoice's scanned document lives, and how to reach it."""
from __future__ import annotations

from sqlmodel import Session, select

from .db.models import ErpAccount, ErpEntry, ErpIntegration, Invoice


def resolve_document_source(
    session: Session, invoice: Invoice
) -> tuple[ErpIntegration, str] | None:
    """Which integration holds this invoice's document, and under which voucher."""
    row = session.exec(
        select(ErpEntry, ErpAccount)
        .join(ErpAccount, ErpAccount.id == ErpEntry.erp_account_id)
        .where(
            ErpEntry.source_invoice_id == invoice.id,
            ErpEntry.company_id == invoice.company_id,
            ErpEntry.voucher_id.is_not(None),
        )
        .order_by(ErpEntry.id)
    ).first()
    if row is None:
        return None

    entry, account = row
    integration = session.get(ErpIntegration, account.erp_integration_id)
    if (
        integration is None
        or integration.disconnected_at is not None
        or integration.company_id != invoice.company_id
    ):
        return None
    return integration, str(entry.voucher_id)
