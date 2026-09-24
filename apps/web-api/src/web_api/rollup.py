"""Invoice status rollup — derive ``Invoice.status`` from its lines.

Kept as a shared helper so both the AI sync runner (ai_api) and the human verify
endpoint (web_api) recompute the invoice the same way, in the same transaction
as the line change that triggered it. Deriving (rather than storing an
independent value) keeps the invoice and its lines from drifting apart.

Rollup:
- ``uncategorized`` while no line has been categorized yet,
- ``categorized`` once any line has an AI result (or a mix in progress),
- ``verified`` once the invoice has lines and every line is ``verified``.
"""
from __future__ import annotations

from sqlmodel import Session, select

from .db.models import Invoice, InvoiceLine
from .db.models.enums import InvoiceStatus, LineStatus


def recompute_invoice_status(session: Session, invoice_id: str) -> InvoiceStatus | None:
    """Recompute and persist an invoice's rolled-up status. Returns the new value.

    Does not commit — the caller owns the transaction.
    """
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
