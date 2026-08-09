"""The document-processing stage.

Discovers its work from the database exactly as the sync runner does — no tenant
and no credentials as arguments — and turns each pending invoice's attached
document into invoice lines.

    python -m ai_api.documents.runner                     # every pending invoice
    python -m ai_api.documents.runner --limit 20          # pace a backlog
    python -m ai_api.documents.runner --company-id <id>   # one tenant
    python -m ai_api.documents.runner --invoice-id <id>   # one invoice

Failure is isolated per invoice: an unreadable document, an unreachable ERP or a
model that returned nonsense is recorded on that invoice and the run continues.
The process exits non-zero if any invoice failed, so a scheduler can see it.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlmodel import Session, select

from web_api.connectors.base import ErpConnectionError
from web_api.db.models import Company, DocStatus, ErpIntegration, Invoice
from web_api.db.session import engine
from web_api.documents import resolve_document_source
from web_api.fx import FxService
from web_api import integrations as integrations_mod

from .. import config
from .extractor import EmptyDocumentError, UnsupportedMediaError, extract_lines
from .reconcile import reconcile
from .replace import replace_invoice_lines

logger = logging.getLogger("ai_api.documents")

_ZERO = Decimal("0")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# -- Work discovery ----------------------------------------------------------


def pending_invoices(
    session: Session,
    *,
    company_id: str | None = None,
    invoice_id: str | None = None,
    limit: int | None = None,
) -> list[Invoice]:
    """Invoices waiting for their document to be read.

    Oldest `invoice_date` first, so a backlog drains in the order the spend was
    incurred rather than in whatever order the rows happen to sit in.

    The selectors only *narrow* what the database produced. Naming an invoice
    that is not pending finds nothing — the stage cannot create work, only do
    the work discovery found, which is the same rule the sync runner follows.

    A `processing` invoice whose claim has gone stale is included: its run died
    holding the claim, and without this it would sit unread forever.
    """
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
    # `nulls_last` is not portable across the SQLite suite and PostgreSQL here;
    # ordering by the id as a tiebreak keeps the order deterministic either way.
    statement = statement.order_by(Invoice.invoice_date, Invoice.id)
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.exec(statement).all())


def _claim(session: Session, invoice: Invoice) -> None:
    """Take the invoice, in its own committed transaction.

    Committed *before* any work so two overlapping runs — a cron overlapping its
    predecessor is the ordinary way this happens — cannot both extract the same
    invoice and race each other's replacement. `doc_processed_at` doubles as the
    claim's timestamp, which is what lets a died-mid-run claim go stale.
    """
    invoice.doc_status = DocStatus.PROCESSING
    invoice.doc_processed_at = _now()
    invoice.doc_attempts = (invoice.doc_attempts or 0) + 1
    session.add(invoice)
    session.commit()


def _fail(session: Session, invoice: Invoice, reason: str) -> None:
    """Record why this invoice could not be processed, and keep its lines.

    The invoice's existing lines are deliberately untouched: stand-in lines are
    a correct if coarse answer, and replacing them with nothing would make the
    voucher's spend disappear from the reports over a document problem.
    """
    invoice.doc_status = DocStatus.FAILED
    invoice.doc_error = reason
    session.add(invoice)
    session.commit()
    logger.warning("  invoice %s: %s", invoice.id, reason)


# -- One invoice -------------------------------------------------------------


def process_invoice(
    session: Session, invoice: Invoice, *, extract=extract_lines
) -> str:
    """Read one invoice's document and replace its lines. Returns a status word.

    ``extract`` is the seam the tests stub, so the suite exercises discovery,
    claiming, reconciliation and replacement without a network or a live model.
    """
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
    except (UnsupportedMediaError, EmptyDocumentError) as exc:
        _fail(session, invoice, str(exc))
        return "failed"

    if not extracted.lines:
        _fail(session, invoice, "the document yielded no lines")
        return "failed"

    lines_total = sum((Decimal(str(item.amount)) for item in extracted.lines), _ZERO)
    verdict = reconcile(lines_total, invoice.total, invoice.tax)
    if not verdict.ok:
        _fail(session, invoice, verdict.reason or "the extracted lines do not reconcile")
        return "rejected"

    company = session.get(Company, invoice.company_id)
    base_currency = company.base_currency if company is not None else None
    fx = FxService(session)
    n_removed, n_written = replace_invoice_lines(
        session, invoice, extracted, fx=fx, base_currency=base_currency
    )
    session.commit()
    logger.info(
        "  invoice %s: %d lines extracted, %d replaced%s",
        invoice.id, n_written, n_removed,
        "" if verdict.checked else " (no total to reconcile against)",
    )
    return "processed"


# -- The run -----------------------------------------------------------------


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
            except Exception as exc:  # noqa: BLE001 - one bad document is not the run
                session.rollback()
                _fail(session, invoice, f"extraction crashed: {exc}")
                outcome = "failed"
            counts[outcome] = counts.get(outcome, 0) + 1

    return counts


# -- CLI ---------------------------------------------------------------------


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
    # A scheduler still needs to see that something broke, even though the rest
    # of the backlog was processed.
    return 1 if counts["failed"] or counts["rejected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
