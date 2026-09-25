"""The document-processing stage: discovery, claiming, reconciliation, failure."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from ai_api import config
from ai_api.documents import runner as docs
from ai_api.documents.content import ExtractedLines
from ai_api.documents.errors import (
    EmptyDocumentError,
    UnsupportedMediaError,
    VisionUnreadableError,
)
from ai_api.models import LineItem
from ai_api.sync import runner as sync_runner
from ai_api_testkit import BALANCED_VOUCHER, SCAN_WITHOUT_LINES, TYPED_ACCOUNTS
from web_api.connectors.base import DocumentPayload, ErpConnectionError
from web_api.db.models import (
    AuditLog,
    DocStatus,
    ErpAccount,
    ErpEntry,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    LineOrigin,
    LineStatus,
)
from web_api.reconcile import reconcile_lines


@pytest.fixture(autouse=True)
def _stage_engine(engine, monkeypatch):
    """Point the document stage at the test engine."""
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


def _crashing_extractor(payload: DocumentPayload) -> ExtractedLines:
    raise RuntimeError("extraction crashed")


def _invoice(engine) -> Invoice:
    with Session(engine) as s:
        return s.exec(select(Invoice)).one()


def _lines(engine) -> list[InvoiceLine]:
    with Session(engine) as s:
        return list(s.exec(select(InvoiceLine).order_by(InvoiceLine.description)).all())


def test_the_stage_finds_its_own_work(engine, synced):
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
    seen: list[DocStatus] = []

    def _extract(payload):
        with Session(engine) as s:
            seen.append(s.exec(select(Invoice)).one().doc_status)
        return ExtractedLines(lines=[LineItem(description="x", amount=1000.0)])

    docs.run_documents(extract=_extract)

    assert seen == [DocStatus.PROCESSING], (
        "the invoice must already read `processing` by the time work begins"
    )


def test_lines_that_add_up_are_accepted(engine, synced):
    counts = docs.run_documents(extract=_extractor("600.00", "400.00"))

    assert counts["processed"] == 1
    assert [l.amount for l in _lines(engine)] == [Decimal("600.00"), Decimal("400.00")]


def test_lines_stated_net_of_vat_reconcile(engine, synced):
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
    before = _lines(engine)

    docs.run_documents(extract=_extractor("300.00"))

    after = _lines(engine)
    assert [l.id for l in after] == [l.id for l in before]
    assert [l.origin for l in after] == [LineOrigin.ENTRY_FALLBACK]


def test_rounding_does_not_reject(engine, synced):
    counts = docs.run_documents(extract=_extractor("1000.01"))

    assert counts["processed"] == 1


def test_an_invoice_with_no_total_skips_the_check(engine, synced):
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


def test_an_unreadable_scan_fails_cleanly_rather_than_as_a_crash(engine, synced):
    def _extract(payload):
        raise VisionUnreadableError("none of the 3 page(s) of this document could be read")

    counts = docs.run_documents(extract=_extract)

    assert counts["failed"] == 1
    invoice = _invoice(engine)
    assert invoice.doc_status == DocStatus.FAILED
    assert "could be read" in invoice.doc_error
    assert "crashed" not in invoice.doc_error
    assert [l.origin for l in _lines(engine)] == [LineOrigin.ENTRY_FALLBACK]


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
    monkeypatch.setattr(docs, "extract_lines", _crashing_extractor)

    assert docs.main([]) == 1


def test_the_cli_on_an_empty_queue_exits_zero(engine):
    assert docs.main([]) == 0


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


def test_an_accepted_extraction_also_reads_as_reconciled(engine, synced):
    docs.run_documents(extract=_extractor("1000.00"))

    assert _invoice(engine).doc_status == DocStatus.PROCESSED
    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        lines = s.exec(select(InvoiceLine)).all()
        assert reconcile_lines(lines, invoice).ok


def test_a_removed_line_records_that_a_human_had_settled_it(engine, synced):
    with Session(engine) as s:
        line = s.exec(select(InvoiceLine)).one()
        line.description = "Corrected by hand"
        line.verified_fields = ["description"]
        s.add(line)
        s.commit()
        removed_id = line.id

    docs.run_documents(extract=_extractor("1000.00"))

    with Session(engine) as s:
        row = s.exec(
            select(AuditLog).where(
                AuditLog.entity_id == removed_id,
                AuditLog.action == "superseded_by_extraction",
            )
        ).one()
    recorded = {c["field"]: c["old"] for c in row.changes}
    assert recorded["description"] == "Corrected by hand"
    assert recorded["verified_fields"] == ["description"]


def test_processing_state_is_recorded_on_success(engine, synced):
    docs.run_documents(extract=_extractor("1000.00"))

    invoice = _invoice(engine)
    assert invoice.doc_status == DocStatus.PROCESSED
    assert invoice.doc_processed_at is not None
    assert invoice.doc_error is None


def test_doc_status_does_not_disturb_the_categorization_rollup(engine, synced):
    before = _invoice(engine).status

    docs.run_documents(extract=_crashing_extractor)

    invoice = _invoice(engine)
    assert invoice.doc_status == DocStatus.FAILED
    assert invoice.status == before


def _extractor_with(lines, *, invoice_number: str | None = None):
    def _extract(payload: DocumentPayload) -> ExtractedLines:
        return ExtractedLines(lines=lines, invoice_number=invoice_number)

    return _extract


def test_a_lines_unit_is_taken_from_the_document(engine, synced):
    extract = _extractor_with(
        [LineItem(description='Consulting', quantity=12.0, unit_type='hours', amount=1000.0)]
    )

    docs.run_documents(extract=extract)

    (line,) = _lines(engine)
    assert line.quantity == Decimal('12.0000')
    assert line.unit == 'hours'


def test_a_line_the_document_gave_no_unit_for_stores_none(engine, synced):
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
    extract = _extractor_with([LineItem(description='x', amount=1000.0)])

    docs.run_documents(extract=extract)

    assert _invoice(engine).document_invoice_number is None


def _extractor_with_charge():
    """Three products and the freight the totals block charged for them."""
    def _extract(payload: DocumentPayload) -> ExtractedLines:
        return ExtractedLines(
            lines=[
                LineItem(item_name="Cloud hosting March", amount=800.0),
                LineItem(item_name="Shipping", amount=200.0),
            ],
            currency="DKK",
        )

    return _extract


def test_a_charge_line_is_written_like_any_other(engine, synced):
    counts = docs.run_documents(extract=_extractor_with_charge())
    assert counts["processed"] == 1

    lines = sorted(_lines(engine), key=lambda l: l.sequence)
    assert [l.item_name for l in lines] == ["Cloud hosting March", "Shipping"]

    product, shipping = lines
    assert shipping.origin == product.origin == LineOrigin.DOCUMENT_AI
    assert shipping.status == product.status == LineStatus.UNCATEGORIZED
    assert shipping.amount == Decimal("200.00")


def test_a_charge_line_is_picked_up_by_the_categorizer(engine, synced):
    docs.run_documents(extract=_extractor_with_charge())

    with Session(engine) as s:
        integration_id = s.exec(select(ErpAccount.erp_integration_id)).first()
        invoice_ids = list(
            s.exec(
                select(ErpEntry.source_invoice_id)
                .join(ErpAccount, ErpEntry.erp_account_id == ErpAccount.id)
                .where(
                    ErpAccount.erp_integration_id == integration_id,
                    ErpEntry.source_invoice_id.is_not(None),
                )
                .distinct()
            ).all()
        )
        pending = list(
            s.exec(
                select(InvoiceLine).where(
                    InvoiceLine.invoice_id.in_(invoice_ids),
                    InvoiceLine.status == LineStatus.UNCATEGORIZED,
                )
            ).all()
        )

    assert sorted(l.item_name for l in pending) == ["Cloud hosting March", "Shipping"]


def _aquatuning():
    """`F10566081`, with its real figures."""
    def _extract(payload: DocumentPayload) -> ExtractedLines:
        return ExtractedLines(
            currency="DKK",
            total=104.85, tax=20.97, subtotal=83.88,
            lines=[
                LineItem(item_name="Double Protect Ultra", subtotal=29.31,
                         tax_amount=7.33, vat_rate=25.0, amount=36.64),
                LineItem(item_name="Loop Cleaner", amount=31.41, discount=1.50),
                LineItem(item_name="Wärmeleitpaste", amount=20.90),
                LineItem(item_name="Shipping", amount=15.90),
            ],
        )

    return _extract


def test_the_documents_totals_are_stored_and_the_posted_ones_are_not_touched(
    engine, synced
):
    docs.run_documents(extract=_aquatuning())

    invoice = _invoice(engine)
    assert invoice.document_total == Decimal("104.85")
    assert invoice.document_tax == Decimal("20.97")
    assert invoice.document_subtotal == Decimal("83.88")
    assert invoice.total == Decimal("1000.00")
    assert invoice.tax == Decimal("200.00")


def test_a_line_keeps_the_tax_figures_its_document_printed(engine, synced):
    docs.run_documents(extract=_aquatuning())

    lines = {l.item_name: l for l in _lines(engine)}
    protect = lines["Double Protect Ultra"]
    assert protect.subtotal == Decimal("29.31")
    assert protect.tax_amount == Decimal("7.33")
    assert protect.tax_rate == Decimal("25.000")
    assert protect.amount == Decimal("36.64"), "the printed total is not rewritten"

    assert lines["Loop Cleaner"].discount == Decimal("1.50")
    assert lines["Wärmeleitpaste"].subtotal is None
    assert lines["Wärmeleitpaste"].tax_amount is None


def test_a_ledger_disagreement_is_accepted_and_flagged(engine, synced):
    counts = docs.run_documents(extract=_aquatuning())

    assert counts == {"processed": 1, "failed": 0, "rejected": 0}

    invoice = _invoice(engine)
    assert invoice.doc_status == DocStatus.PROCESSED
    assert invoice.doc_error is None
    assert len(_lines(engine)) == 4


def test_lines_that_miss_the_documents_own_total_are_still_rejected(engine, synced):
    def _extract(payload: DocumentPayload) -> ExtractedLines:
        return ExtractedLines(
            currency="DKK", total=104.85,
            lines=[LineItem(item_name="Loop Cleaner", amount=31.41)],
        )

    counts = docs.run_documents(extract=_extract)

    assert counts["rejected"] == 1
    invoice = _invoice(engine)
    assert invoice.doc_status == DocStatus.FAILED
    assert "document" in invoice.doc_error.lower()
    assert [l.origin for l in _lines(engine)] == [LineOrigin.ENTRY_FALLBACK]


def test_a_document_stating_no_total_falls_back_to_the_ledger(engine, synced):
    counts = docs.run_documents(extract=_extractor("1000.00"))

    assert counts["processed"] == 1
    assert _invoice(engine).document_total is None
