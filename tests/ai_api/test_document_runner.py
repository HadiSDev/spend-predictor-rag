"""The document-processing stage: discovery, claiming, reconciliation, failure.

No network and no live model anywhere in here. The stage takes its extractor as
a parameter precisely so this suite can drive it: what is under test is the
orchestration — which invoices are picked up, in what order, what happens to the
ones that fail, and that a failure never costs an invoice the lines it already
had.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from ai_api import config
from ai_api.documents import runner as docs
from ai_api.documents.extractor import EmptyDocumentError, ExtractedLines, UnsupportedMediaError
from ai_api.models import LineItem
from ai_api.sync import runner as sync_runner
from web_api.connectors.base import DocumentPayload, ErpConnectionError
from web_api.db.models import (
    AuditLog,
    DocStatus,
    ErpEntry,
    Invoice,
    InvoiceLine,
    LineOrigin,
    LineStatus,
)

from .test_sync_standin_lines import BALANCED_VOUCHER, SCAN_WITHOUT_LINES, TYPED_ACCOUNTS


@pytest.fixture(autouse=True)
def _stage_engine(engine, monkeypatch):
    """The stage opens its own session, so it needs the throwaway engine too."""
    monkeypatch.setattr(docs, "engine", engine)
    return engine


@pytest.fixture
def synced(engine, fake_connector, make_tenant):
    """One tenant, synced: a documented invoice standing on one stand-in line."""
    fake_connector.accounts = TYPED_ACCOUNTS
    fake_connector.entries = BALANCED_VOUCHER
    fake_connector.scan = SCAN_WITHOUT_LINES
    tenant = make_tenant("Acme")
    sync_runner.run_sync()
    return tenant


def _extractor(*amounts: str, description: str = "Extracted line"):
    """An extractor stub that always returns these line amounts."""
    def _extract(payload: DocumentPayload) -> ExtractedLines:
        return ExtractedLines(
            lines=[
                LineItem(description=f"{description} {i + 1}", amount=float(a))
                for i, a in enumerate(amounts)
            ]
        )

    return _extract


def _document(media_type: str = "application/pdf") -> DocumentPayload:
    return DocumentPayload(content=b"%PDF-1.4 fake", media_type=media_type,
                           filename="inv-1.pdf")


@pytest.fixture(autouse=True)
def _serves_a_document(fake_connector, monkeypatch):
    """The fake connector hands back a document, so the stage has bytes to read."""
    monkeypatch.setattr(
        fake_connector, "fetch_invoice_document",
        lambda self, voucher_id: _document(), raising=False,
    )


def _invoice(engine) -> Invoice:
    with Session(engine) as s:
        return s.exec(select(Invoice)).one()


def _lines(engine) -> list[InvoiceLine]:
    with Session(engine) as s:
        return list(s.exec(select(InvoiceLine).order_by(InvoiceLine.description)).all())


# -- Discovery ---------------------------------------------------------------


def test_the_stage_finds_its_own_work(engine, synced):
    """No tenant on the command line: the pending invoice is discovered."""
    counts = docs.run_documents(extract=_extractor("1000.00"))

    assert counts["processed"] == 1
    assert _invoice(engine).doc_status == DocStatus.PROCESSED


def test_an_invoice_with_no_document_is_never_picked_up(engine, fake_connector, make_tenant):
    fake_connector.accounts = TYPED_ACCOUNTS
    fake_connector.entries = BALANCED_VOUCHER
    fake_connector.scan = SCAN_WITHOUT_LINES.model_copy(
        update={"file_name": None, "file_ref": None}
    )
    make_tenant("Acme")
    sync_runner.run_sync()

    counts = docs.run_documents(extract=_extractor("1000.00"))

    assert counts == {"processed": 0, "failed": 0, "rejected": 0}
    assert _invoice(engine).doc_status == DocStatus.NOT_APPLICABLE


def test_a_selector_narrows_but_never_invents(engine, synced):
    """Naming an invoice that is not pending finds nothing — it creates nothing."""
    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        invoice_id = invoice.id
        invoice.doc_status = DocStatus.PROCESSED
        s.add(invoice)
        s.commit()

    counts = docs.run_documents(invoice_id=invoice_id, extract=_extractor("1000.00"))

    assert counts == {"processed": 0, "failed": 0, "rejected": 0}


def test_the_attempt_ceiling_stops_the_retrying(engine, synced, monkeypatch):
    monkeypatch.setattr(config, "DOC_MAX_ATTEMPTS", 1)
    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        invoice.doc_attempts = 1
        s.add(invoice)
        s.commit()

    counts = docs.run_documents(extract=_extractor("1000.00"))

    assert counts == {"processed": 0, "failed": 0, "rejected": 0}


def test_an_abandoned_claim_is_picked_up_again(engine, synced, monkeypatch):
    """A run that died holding the claim must not strand the invoice forever."""
    monkeypatch.setattr(config, "DOC_STALE_CLAIM_MINUTES", 30)
    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        invoice.doc_status = DocStatus.PROCESSING
        invoice.doc_processed_at = datetime.now(timezone.utc) - timedelta(hours=2)
        s.add(invoice)
        s.commit()

    counts = docs.run_documents(extract=_extractor("1000.00"))

    assert counts["processed"] == 1


def test_a_fresh_claim_is_left_alone(engine, synced, monkeypatch):
    """Two overlapping runs must not both take the same invoice."""
    monkeypatch.setattr(config, "DOC_STALE_CLAIM_MINUTES", 30)
    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        invoice.doc_status = DocStatus.PROCESSING
        invoice.doc_processed_at = datetime.now(timezone.utc)
        s.add(invoice)
        s.commit()

    counts = docs.run_documents(extract=_extractor("1000.00"))

    assert counts == {"processed": 0, "failed": 0, "rejected": 0}


def test_the_invoice_is_claimed_before_the_document_is_fetched(engine, synced):
    """The claim is committed first, or a concurrent run would take it too."""
    seen: list[DocStatus] = []

    def _extract(payload):
        with Session(engine) as s:
            seen.append(s.exec(select(Invoice)).one().doc_status)
        return ExtractedLines(lines=[LineItem(description="x", amount=1000.0)])

    docs.run_documents(extract=_extract)

    assert seen == [DocStatus.PROCESSING], (
        "the invoice must already read `processing` by the time work begins"
    )


# -- Reconciliation ----------------------------------------------------------


def test_lines_that_add_up_are_accepted(engine, synced):
    """The invoice is 1000.00 gross."""
    counts = docs.run_documents(extract=_extractor("600.00", "400.00"))

    assert counts["processed"] == 1
    assert [l.amount for l in _lines(engine)] == [Decimal("600.00"), Decimal("400.00")]


def test_lines_stated_net_of_vat_reconcile(engine, synced):
    """1000.00 gross carrying 200.00 tax — a document may state either figure."""
    counts = docs.run_documents(extract=_extractor("800.00"))

    assert counts["processed"] == 1


def test_a_missed_line_is_rejected(engine, synced):
    counts = docs.run_documents(extract=_extractor("300.00"))

    assert counts["rejected"] == 1
    invoice = _invoice(engine)
    assert invoice.doc_status == DocStatus.FAILED
    assert "300.0" in invoice.doc_error and "1000.00" in invoice.doc_error, (
        f"the failure must name both sums, got {invoice.doc_error!r}"
    )


def test_a_rejected_extraction_keeps_the_lines_it_had(engine, synced):
    """Replacing coarse-but-correct lines with nothing would erase real spend."""
    before = _lines(engine)

    docs.run_documents(extract=_extractor("300.00"))

    after = _lines(engine)
    assert [l.id for l in after] == [l.id for l in before]
    assert [l.origin for l in after] == [LineOrigin.ENTRY_FALLBACK]


def test_rounding_does_not_reject(engine, synced):
    counts = docs.run_documents(extract=_extractor("1000.01"))

    assert counts["processed"] == 1


def test_an_invoice_with_no_total_skips_the_check(engine, synced):
    """Nothing to reconcile against is not the same as failing to reconcile."""
    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        invoice.total = None
        invoice.tax = None
        s.add(invoice)
        s.commit()

    counts = docs.run_documents(extract=_extractor("7.00"))

    assert counts["processed"] == 1


def test_a_document_that_yields_no_lines_fails(engine, synced):
    counts = docs.run_documents(extract=lambda payload: ExtractedLines(lines=[]))

    assert counts["failed"] == 1
    assert "no lines" in _invoice(engine).doc_error


# -- Failure is isolated and never destructive -------------------------------


def test_an_unsupported_media_type_fails_cleanly(engine, synced):
    def _extract(payload):
        raise UnsupportedMediaError("inv-1.jpg: no extractor for media type 'image/jpeg'")

    counts = docs.run_documents(extract=_extract)

    assert counts["failed"] == 1
    invoice = _invoice(engine)
    assert invoice.doc_status == DocStatus.FAILED
    assert "image/jpeg" in invoice.doc_error
    assert [l.origin for l in _lines(engine)] == [LineOrigin.ENTRY_FALLBACK]


def test_a_pdf_with_no_text_layer_fails_cleanly(engine, synced):
    def _extract(payload):
        raise EmptyDocumentError("inv-1.pdf: the PDF has no extractable text layer")

    counts = docs.run_documents(extract=_extract)

    assert counts["failed"] == 1
    assert "text layer" in _invoice(engine).doc_error


def test_a_crash_is_recorded_rather_than_raised(engine, synced):
    def _extract(payload):
        raise RuntimeError("the model returned nonsense")

    counts = docs.run_documents(extract=_extract)

    assert counts["failed"] == 1
    assert "the model returned nonsense" in _invoice(engine).doc_error


def test_a_document_the_erp_has_dropped_fails(engine, synced, fake_connector, monkeypatch):
    monkeypatch.setattr(
        fake_connector, "fetch_invoice_document",
        lambda self, voucher_id: None, raising=False,
    )

    counts = docs.run_documents(extract=_extractor("1000.00"))

    assert counts["failed"] == 1
    assert "no longer has a document" in _invoice(engine).doc_error


def test_an_unreachable_erp_fails_only_that_invoice(engine, synced, fake_connector, monkeypatch):
    def _boom(self, voucher_id):
        raise ErpConnectionError("connection refused")

    monkeypatch.setattr(fake_connector, "fetch_invoice_document", _boom, raising=False)

    counts = docs.run_documents(extract=_extractor("1000.00"))

    assert counts["failed"] == 1
    assert "could not reach the ERP" in _invoice(engine).doc_error


def test_one_bad_invoice_does_not_stop_the_run(engine, fake_connector, make_tenant):
    """Two tenants, one extraction that blows up: the other still lands."""
    fake_connector.accounts = TYPED_ACCOUNTS
    fake_connector.entries = BALANCED_VOUCHER
    fake_connector.scan = SCAN_WITHOUT_LINES
    make_tenant("Acme")
    make_tenant("Globex")
    sync_runner.run_sync()

    calls: list[str] = []

    def _extract(payload):
        calls.append("call")
        if len(calls) == 1:
            raise RuntimeError("first one blew up")
        return ExtractedLines(lines=[LineItem(description="ok", amount=1000.0)])

    counts = docs.run_documents(extract=_extract)

    assert counts == {"processed": 1, "failed": 1, "rejected": 0}


def test_the_cli_exits_non_zero_when_an_invoice_failed(engine, synced, monkeypatch):
    monkeypatch.setattr(
        docs, "extract_lines", lambda payload: (_ for _ in ()).throw(RuntimeError("nope"))
    )

    assert docs.main([]) == 1


def test_the_cli_on_an_empty_queue_exits_zero(engine):
    assert docs.main([]) == 0


# -- Replacement -------------------------------------------------------------


def test_standins_are_fully_replaced(engine, synced):
    docs.run_documents(extract=_extractor("600.00", "400.00"))

    lines = _lines(engine)
    assert [l.origin for l in lines] == [LineOrigin.DOCUMENT_AI] * 2, (
        "an invoice holds exactly one origin — a stand-in left beside an "
        "extracted line would double-count the invoice"
    )
    assert all(l.status == LineStatus.UNCATEGORIZED for l in lines), (
        "the stage never categorizes; the categorizer does, on its own schedule"
    )


def test_a_removed_line_is_on_the_record(engine, synced):
    """The audit row is the only trace a replaced line ever existed."""
    with Session(engine) as s:
        line = s.exec(select(InvoiceLine)).one()
        line.status = LineStatus.VERIFIED
        line.level_1 = "Indirect"
        line.level_2 = "IT"
        s.add(line)
        s.commit()
        removed_id = line.id

    docs.run_documents(extract=_extractor("1000.00"))

    with Session(engine) as s:
        rows = s.exec(
            select(AuditLog).where(AuditLog.entity_id == removed_id)
        ).all()
    superseded = [r for r in rows if r.action == "superseded_by_extraction"]
    assert len(superseded) == 1, f"expected one supersede row, got {rows}"
    changes = {c["field"]: c["old"] for c in superseded[0].changes}
    assert changes["status"] == "verified"
    assert changes["level_2"] == "IT"
    assert superseded[0].actor == "system"


def test_an_uncategorized_removal_is_recorded_too(engine, synced):
    """The invoice's history is complete, not selective."""
    removed_id = _lines(engine)[0].id

    docs.run_documents(extract=_extractor("1000.00"))

    with Session(engine) as s:
        rows = s.exec(
            select(AuditLog).where(
                AuditLog.entity_id == removed_id,
                AuditLog.action == "superseded_by_extraction",
            )
        ).all()
    assert len(rows) == 1


def test_replacement_resets_a_verified_invoice(engine, synced):
    """Leaving it verified would assert a judgement over lines no human has seen."""
    from web_api.db.models import InvoiceStatus

    with Session(engine) as s:
        line = s.exec(select(InvoiceLine)).one()
        line.status = LineStatus.VERIFIED
        s.add(line)
        invoice = s.exec(select(Invoice)).one()
        invoice.status = InvoiceStatus.VERIFIED
        s.add(invoice)
        s.commit()

    docs.run_documents(extract=_extractor("1000.00"))

    assert _invoice(engine).status == InvoiceStatus.UNCATEGORIZED


def test_postings_are_unlinked_by_replacement(engine, synced):
    """An extracted line has no ERP identity, so no posting may claim it."""
    with Session(engine) as s:
        linked = s.exec(
            select(ErpEntry).where(ErpEntry.source_invoice_line_id.is_not(None))
        ).all()
    assert linked, "precondition: the stand-in was linked to its posting"

    docs.run_documents(extract=_extractor("1000.00"))

    with Session(engine) as s:
        still_linked = s.exec(
            select(ErpEntry).where(ErpEntry.source_invoice_line_id.is_not(None))
        ).all()
    assert still_linked == [], "a posting must not point at an extracted line"


def test_a_second_extraction_leaves_one_set_of_lines(engine, synced):
    docs.run_documents(extract=_extractor("1000.00"))
    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        invoice.doc_status = DocStatus.PENDING
        s.add(invoice)
        s.commit()

    docs.run_documents(extract=_extractor("600.00", "400.00"))

    assert len(_lines(engine)) == 2


def test_processing_state_is_recorded_on_success(engine, synced):
    docs.run_documents(extract=_extractor("1000.00"))

    invoice = _invoice(engine)
    assert invoice.doc_status == DocStatus.PROCESSED
    assert invoice.doc_processed_at is not None
    assert invoice.doc_error is None


def test_doc_status_does_not_disturb_the_categorization_rollup(engine, synced):
    """The two statuses answer different questions and must move independently.

    The sync already categorized the stand-in line, so the invoice reads
    `categorized`. A failed extraction must leave that exactly as it is: whether
    we could read the document says nothing about whether the spend is
    categorized.
    """
    before = _invoice(engine).status

    docs.run_documents(extract=lambda payload: (_ for _ in ()).throw(RuntimeError("no")))

    invoice = _invoice(engine)
    assert invoice.doc_status == DocStatus.FAILED
    assert invoice.status == before


# -- Unit of measure, and the number printed on the document -----------------


def _extractor_with(lines, *, invoice_number: str | None = None):
    def _extract(payload: DocumentPayload) -> ExtractedLines:
        return ExtractedLines(lines=lines, invoice_number=invoice_number)

    return _extract


def test_a_lines_unit_is_taken_from_the_document(engine, synced):
    """A bare quantity is ambiguous: 12 against "Consulting" is hours or days."""
    extract = _extractor_with(
        [LineItem(description='Consulting', quantity=12.0, unit_type='hours', amount=1000.0)]
    )

    docs.run_documents(extract=extract)

    (line,) = _lines(engine)
    assert line.quantity == Decimal('12.0000')
    assert line.unit == 'hours'


def test_a_line_the_document_gave_no_unit_for_stores_none(engine, synced):
    """Never defaulted: "pcs" assumed over an hourly line is confidently wrong."""
    extract = _extractor_with(
        [LineItem(description='Consulting', quantity=12.0, amount=1000.0)]
    )

    docs.run_documents(extract=extract)

    assert _lines(engine)[0].unit is None


def test_a_blank_unit_is_stored_as_none(engine, synced):
    extract = _extractor_with(
        [LineItem(description='Consulting', quantity=12.0, unit_type='  ', amount=1000.0)]
    )

    docs.run_documents(extract=extract)

    assert _lines(engine)[0].unit is None


def test_the_printed_invoice_number_lands_beside_the_posted_one(engine, synced):
    """Billy's posted number is often the bill id — the real one is on the scan."""
    posted = _invoice(engine).invoice_number
    extract = _extractor_with(
        [LineItem(description='x', amount=1000.0)], invoice_number='2026-0412'
    )

    docs.run_documents(extract=extract)

    invoice = _invoice(engine)
    assert invoice.document_invoice_number == '2026-0412'
    assert invoice.invoice_number == posted, (
        "the as-posted number is evidence of what the ERP holds and is never "
        "rewritten — the same rule that keeps `total` beside `base_total`"
    )


def test_a_document_stating_no_number_stores_none(engine, synced):
    """Not filled from the posted value: that would make "read from the
    document" indistinguishable from "copied from the ledger"."""
    extract = _extractor_with([LineItem(description='x', amount=1000.0)])

    docs.run_documents(extract=extract)

    assert _invoice(engine).document_invoice_number is None
