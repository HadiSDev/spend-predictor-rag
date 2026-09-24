"""Where an invoice's scanned document lives, and how to reach it.

One rule, two callers: `GET /invoices/{id}/document` streams the document to a
browser, and the ai_api document stage reads the same bytes to extract lines from
them. They must agree on *which* voucher of *which* integration holds the scan —
two implementations of that would eventually serve a browser one document and
hand the extractor another.

The web layer is not imported here: this returns ``None`` rather than raising an
``HTTPException``, and each caller maps that to whatever "not found" means for it.
"""
from __future__ import annotations

from sqlmodel import Session, select

from .db.models import ErpAccount, ErpEntry, ErpIntegration, Invoice


def resolve_document_source(
    session: Session, invoice: Invoice
) -> tuple[ErpIntegration, str] | None:
    """Which integration holds this invoice's document, and under which voucher.

    An invoice carries no integration id. The only path is through its
    postings: entry -> erp_account -> erp_integration, and every hop is
    re-scoped to the invoice's own company — an entry is trusted to name its
    integration, but never trusted to name one belonging to a *different*
    tenant, which a single bad sync row could otherwise cause.

    There is deliberately no fallback. Guessing a voucher id (the old
    fallback used `invoice.invoice_number`) is wrong on its face: a supplier's
    invoice number and the ERP's own voucher sequence are different
    namespaces, and a numeric supplier number can collide with a real voucher
    id and serve a document belonging to a different transaction entirely.
    Likewise, if the posting's own integration is disconnected, that is a
    dead end, not a cue to ask a *different* integration with a *different*
    key — the true voucher id was already in hand and is not transferable.
    """
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
