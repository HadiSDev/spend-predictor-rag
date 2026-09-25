"""Swap an invoice's provisional lines for the ones the document stated."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlmodel import Session, select

from web_api.audit import (
    LINE_AUDIT_FIELDS,
    LINE_VALUE_AUDIT_FIELDS,
    _norm,
    record_audit,
)
from web_api.db.models import (
    DocStatus,
    ErpEntry,
    Invoice,
    InvoiceLine,
    LineOrigin,
    LineStatus,
)
from web_api.db.models.audit_log import SYSTEM_ACTOR
from web_api.fx import FxService
from web_api.fx.service import convert as fx_convert
from web_api.rollup import recompute_invoice_status

from .content import ExtractedLines

logger = logging.getLogger("ai_api.documents")

REPLACED_ACTION = "superseded_by_extraction"

_REMOVED_FIELDS = (
    *LINE_VALUE_AUDIT_FIELDS,
    "native_account_code",
    "origin",
    "verified_fields",
    *LINE_AUDIT_FIELDS,
)


def _name_and_description(item) -> tuple[str | None, str | None]:
    """Split one extracted line into the thing bought and the prose about it."""
    name = (item.item_name or "").strip() or None
    description = (item.description or "").strip() or None
    if name is None:
        return description, None
    if description == name:
        return name, None
    return name, description


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _money(value, rate: Decimal | None) -> Decimal | None:
    """A money figure restated in the invoice's currency."""
    amount = _dec(value)
    if amount is None or rate is None or rate == 1:
        return amount
    return fx_convert(amount, rate)


def replace_invoice_lines(
    session: Session,
    invoice: Invoice,
    extracted: ExtractedLines,
    *,
    fx: FxService,
    base_currency: str | None,
    rate: Decimal | None = None,
    document_total: Decimal | None = None,
    document_tax: Decimal | None = None,
    document_subtotal: Decimal | None = None,
) -> tuple[int, int]:
    """Replace the invoice's provisional lines with ``lines``."""
    lines = extracted.lines
    existing = list(
        session.exec(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice.id)
            .order_by(InvoiceLine.id)
        ).all()
    )
    removed_ids = [line.id for line in existing]

    if removed_ids:
        for entry in session.exec(
            select(ErpEntry).where(ErpEntry.source_invoice_line_id.in_(removed_ids))  # type: ignore[union-attr]
        ).all():
            entry.source_invoice_line_id = None
            session.add(entry)

    for line in existing:
        record_audit(
            session,
            entity_type="invoice_line",
            entity_id=line.id,
            action=REPLACED_ACTION,
            actor=SYSTEM_ACTOR,
            changes=[
                {"field": field, "old": _audit_value(line, field), "new": None}
                for field in _REMOVED_FIELDS
            ],
        )
        session.delete(line)

    for seq, item in enumerate(lines):
        name, description = _name_and_description(item)
        row = InvoiceLine(
            company_id=invoice.company_id,
            invoice_id=invoice.id,
            sequence=seq,
            item_name=name,
            description=description,
            quantity=_dec(item.quantity),
            unit=(item.unit_type or "").strip() or None,
            unit_price=_money(item.unit_price, rate),
            amount=_money(item.amount, rate),
            subtotal=_money(item.subtotal, rate),
            tax_amount=_money(item.tax_amount, rate),
            discount=_money(item.discount, rate),
            tax_rate=_dec(item.vat_rate),
            status=LineStatus.UNCATEGORIZED,
            origin=LineOrigin.DOCUMENT_AI,
        )
        session.add(row)
        if base_currency is not None:
            try:
                fx.convert_line(
                    row, base_currency,
                    currency=invoice.currency, invoice_date=invoice.invoice_date,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("  line conversion failed for invoice %s: %s", invoice.id, exc)

    session.flush()
    recompute_invoice_status(session, invoice.id)

    invoice.document_invoice_number = extracted.invoice_number

    invoice.document_total = document_total
    invoice.document_tax = document_tax
    invoice.document_subtotal = document_subtotal

    invoice.doc_status = DocStatus.PROCESSED
    invoice.doc_processed_at = datetime.now(timezone.utc)
    invoice.doc_error = None
    session.add(invoice)

    return len(removed_ids), len(lines)


def _audit_value(line: InvoiceLine, field: str):
    return _norm(getattr(line, field, None))
