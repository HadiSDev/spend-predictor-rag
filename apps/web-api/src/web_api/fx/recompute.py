"""Rewriting a company's stored base amounts."""
from __future__ import annotations

import logging
from typing import Callable, Iterable

from sqlmodel import Session, select

from ..db.models import Company, ErpEntry, Invoice, InvoiceLine
from .service import CONVERTED, UNCHANGED, UNCONVERTED, FxService

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def recompute_company(
    session: Session,
    company_id: str,
    *,
    fx: FxService | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Recompute one company's base amounts."""
    company = session.get(Company, company_id)
    if company is None:
        raise LookupError(f"no such company: {company_id}")

    fx = fx if fx is not None else FxService(session)
    base_currency = company.base_currency
    counts = {CONVERTED: 0, UNCONVERTED: 0, UNCHANGED: 0}

    invoices = session.exec(
        select(Invoice).where(Invoice.company_id == company_id)
    ).all()
    pending = 0
    for invoice in invoices:
        counts[fx.convert_invoice(invoice, base_currency)] += 1
        lines = session.exec(
            select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
        ).all()
        for line in lines:
            counts[
                fx.convert_line(
                    line, base_currency,
                    currency=invoice.currency, invoice_date=invoice.invoice_date,
                )
            ] += 1
        pending += 1 + len(lines)
        pending = _maybe_flush(session, pending, batch_size)

    _walk(
        session,
        select(ErpEntry).where(ErpEntry.company_id == company_id),
        lambda entry: fx.convert_entry(entry, base_currency),
        counts,
        batch_size,
    )

    session.flush()
    logger.info(
        "FX recompute for %s → %s: %d converted, %d unconverted, %d unchanged",
        company_id, base_currency,
        counts[CONVERTED], counts[UNCONVERTED], counts[UNCHANGED],
    )
    return counts


def _walk(
    session: Session,
    statement,
    convert: Callable[[object], str],
    counts: dict[str, int],
    batch_size: int,
) -> None:
    pending = 0
    for row in session.exec(statement).all():
        counts[convert(row)] += 1
        pending = _maybe_flush(session, pending + 1, batch_size)


def _maybe_flush(session: Session, pending: int, batch_size: int) -> int:
    if pending >= batch_size:
        session.flush()
        return 0
    return pending


def recompute_companies(
    session: Session,
    company_ids: Iterable[str],
    *,
    fx: FxService | None = None,
) -> dict[str, dict[str, int]]:
    """Recompute several companies, sharing one FX service (and one rate memo)."""
    fx = fx if fx is not None else FxService(session)
    return {cid: recompute_company(session, cid, fx=fx) for cid in company_ids}
