"""Invoice status rollup — derive ``Invoice.status`` from its lines."""
from __future__ import annotations

from sqlmodel import Session, select

from .db.models import Invoice, InvoiceLine
from .db.models.enums import InvoiceStatus, LineStatus


def recompute_invoice_status(session: Session, invoice_id: str) -> InvoiceStatus | None:
    """Recompute and persist an invoice's rolled-up status."""
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        return None
    statuses = session.exec(
        select(InvoiceLine.status).where(InvoiceLine.invoice_id == invoice_id)
    ).all()

    if not statuses:
        new_status = InvoiceStatus.UNCATEGORIZED
    elif all(s == LineStatus.VERIFIED for s in statuses):
        new_status = InvoiceStatus.VERIFIED
    elif all(s == LineStatus.UNCATEGORIZED for s in statuses):
        new_status = InvoiceStatus.UNCATEGORIZED
    else:
        new_status = InvoiceStatus.CATEGORIZED

    invoice.status = new_status
    session.add(invoice)
    return new_status
