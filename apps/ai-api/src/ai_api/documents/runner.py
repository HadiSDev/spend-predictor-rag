"""The document-processing stage."""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlmodel import Session, select

from web_api import integrations as integrations_mod
from web_api.connectors.base import ErpConnectionError
from web_api.db.models import Company, DocStatus, Invoice
from web_api.db.session import engine
from web_api.documents import resolve_document_source
from web_api.fx import FxService
from web_api.fx.service import convert as fx_convert

from .. import config
from .currency import conversion_rate
from .errors import EmptyDocumentError, UnsupportedMediaError, VisionUnreadableError
from .extractor import extract_lines
from .reconcile import reconcile
from .replace import replace_invoice_lines

logger = logging.getLogger("ai_api.documents")

_ZERO = Decimal("0")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _converted(value: float | None, rate: Decimal) -> Decimal | None:
    """A figure the document stated, restated in the invoice's currency."""
    if value is None:
        return None
    amount = Decimal(str(value))
    return amount if rate == 1 else fx_convert(amount, rate)


def pending_invoices(
    session: Session,
    *,
    company_id: str | None = None,
    invoice_id: str | None = None,
    limit: int | None = None,
) -> list[Invoice]:
    """Invoices waiting for their document to be read."""
    stale_before = _now() - timedelta(minutes=config.DOC_STALE_CLAIM_MINUTES)
    claimable = Invoice.doc_status == DocStatus.PENDING
    abandoned = (Invoice.doc_status == DocStatus.PROCESSING) & (
        (Invoice.doc_processed_at.is_(None)) | (Invoice.doc_processed_at < stale_before)  # type: ignore[union-attr]
    )
    statement = select(Invoice).where(
        claimable | abandoned,
        Invoice.file_id.is_not(None),  # type: ignore[union-attr]
        Invoice.doc_attempts < config.DOC_MAX_ATTEMPTS,
    )
    if company_id is not None:
        statement = statement.where(Invoice.company_id == company_id)
    if invoice_id is not None:
        statement = statement.where(Invoice.id == invoice_id)
    statement = statement.order_by(Invoice.invoice_date, Invoice.id)
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.exec(statement).all())


def _claim(session: Session, invoice: Invoice) -> None:
    """Take the invoice, in its own committed transaction."""
    invoice.doc_status = DocStatus.PROCESSING
    invoice.doc_processed_at = _now()
    invoice.doc_attempts = (invoice.doc_attempts or 0) + 1
    session.add(invoice)
    session.commit()


def _fail(session: Session, invoice: Invoice, reason: str) -> None:
    """Record why this invoice could not be processed, and keep its lines."""
    invoice.doc_status = DocStatus.FAILED
    invoice.doc_error = reason
    session.add(invoice)
    session.commit()
    logger.warning("  invoice %s: %s", invoice.id, reason)


def process_invoice(
    session: Session, invoice: Invoice, *, extract=extract_lines
) -> str:
    """Read one invoice's document and replace its lines."""
    resolved = resolve_document_source(session, invoice)
    if resolved is None:
        _fail(session, invoice, "cannot determine which ERP holds this document")
        return "failed"
    integration, voucher_id = resolved

    try:
        connector = integrations_mod.connector_for_integration(session, integration)
    except RuntimeError as exc:
        _fail(session, invoice, f"ERP connection unavailable: {exc}")
        return "failed"

    try:
        payload = connector.fetch_invoice_document(voucher_id)
    except ErpConnectionError as exc:
        _fail(session, invoice, f"could not reach the ERP for this document: {exc}")
        return "failed"
    if payload is None:
        _fail(session, invoice, "the ERP no longer has a document for this voucher")
        return "failed"

    try:
        extracted = extract(payload)
    except (UnsupportedMediaError, EmptyDocumentError, VisionUnreadableError) as exc:
        _fail(session, invoice, str(exc))
        return "failed"

    if not extracted.lines:
        _fail(session, invoice, "the document yielded no lines")
        return "failed"

    company = session.get(Company, invoice.company_id)
    base_currency = company.base_currency if company is not None else None
    fx = FxService(session)

    lines_total = sum(
        (Decimal(str(item.amount)) for item in extracted.lines if item.amount is not None),
        _ZERO,
    )
    rate, mismatch = conversion_rate(
        extracted.currency, invoice.currency, invoice.invoice_date, fx
    )
    if rate is None:
        _fail(session, invoice, mismatch or "the document's currency cannot be compared")
        return "rejected"
    comparable = lines_total * rate

    document_total = _converted(extracted.total, rate)
    document_subtotal = _converted(extracted.subtotal, rate)

    verdict = reconcile(
        comparable,
        invoice.total,
        invoice.tax,
        document_total=document_total,
        document_subtotal=document_subtotal,
    )
    if not verdict.ok:
        _fail(session, invoice, verdict.reason or "the extracted lines do not reconcile")
        return "rejected"
    if verdict.totals_agree is False:
        logger.info(
            "  invoice %s: the document states %s where the ledger posted %s — "
            "accepted, and the disagreement recorded for a reviewer",
            invoice.id, document_total, invoice.total,
        )

    n_removed, n_written = replace_invoice_lines(
        session, invoice, extracted, fx=fx, base_currency=base_currency, rate=rate,
        document_total=document_total, document_subtotal=document_subtotal,
        document_tax=_converted(extracted.tax, rate),
    )
    session.commit()
    logger.info(
        "  invoice %s: %d lines extracted, %d replaced%s",
        invoice.id, n_written, n_removed,
        "" if verdict.checked else " (no total to reconcile against)",
    )
    return "processed"


def run_documents(
    *,
    company_id: str | None = None,
    invoice_id: str | None = None,
    limit: int | None = None,
    extract=extract_lines,
) -> dict[str, int]:
    """Process every pending invoice. Returns counts by outcome."""
    counts = {"processed": 0, "failed": 0, "rejected": 0}

    with Session(engine) as session:
        work = pending_invoices(
            session, company_id=company_id, invoice_id=invoice_id, limit=limit
        )
        if not work:
            logger.info(
                "No invoices are waiting for document processing. Run the sync "
                "first, or check that the invoices have a document attached."
            )
            return counts

        logger.info("Processing %d invoice(s)…", len(work))
        for invoice in work:
            _claim(session, invoice)
            try:
                outcome = process_invoice(session, invoice, extract=extract)
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                _fail(session, invoice, f"extraction crashed: {exc}")
                outcome = "failed"
            counts[outcome] = counts.get(outcome, 0) + 1

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Turn pending invoices' attached documents into invoice lines. "
                    "Work is discovered from the database, never named here.",
    )
    parser.add_argument("--company-id", default=None, help="Only this company's invoices")
    parser.add_argument("--invoice-id", default=None, help="Only this invoice")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most this many invoices, to pace a large backlog",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    counts = run_documents(
        company_id=args.company_id, invoice_id=args.invoice_id, limit=args.limit
    )

    if not any(counts.values()):
        if args.invoice_id or args.company_id:
            print("\nThe selector matched no invoice awaiting document processing.")
        return 0

    print("\n=== documents ===")
    for key, value in counts.items():
        print(f"{key}: {value}")
    return 1 if counts["failed"] or counts["rejected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
