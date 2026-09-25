"""Stand-in lines, and the document queue the sync leaves behind."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session, select

from ai_api.sync import runner
from ai_api_testkit import (
    BALANCED_VOUCHER,
    SCAN_WITHOUT_LINES,
    SPLIT_VOUCHER,
    TYPED_ACCOUNTS,
    entry,
)
from web_api.db.models import (
    AuditLog,
    DocStatus,
    ErpEntry,
    Invoice,
    InvoiceLine,
    LineOrigin,
    LineStatus,
)
from web_api.db.models.audit_log import SYSTEM_ACTOR


@pytest.fixture
def scanless(fake_connector):
    """A voucher whose ERP supplies no invoice lines, on a typed chart."""
    fake_connector.accounts = TYPED_ACCOUNTS
    fake_connector.entries = BALANCED_VOUCHER
    fake_connector.scan = SCAN_WITHOUT_LINES
    return fake_connector


def _lines(engine, company_id: str) -> list[InvoiceLine]:
    with Session(engine) as s:
        return list(
            s.exec(
                select(InvoiceLine)
                .where(InvoiceLine.company_id == company_id)
                .order_by(InvoiceLine.native_account_code)
            ).all()
        )


def _invoice(engine, company_id: str) -> Invoice:
    with Session(engine) as s:
        return s.exec(select(Invoice).where(Invoice.company_id == company_id)).one()


def test_a_scanless_voucher_yields_one_line_per_expense_posting(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")

    runner.run_sync()

    lines = _lines(engine, tenant["company_id"])
    assert [l.native_account_code for l in lines] == ["6010"], (
        "expected exactly the expense posting to stand in for a line"
    )
    (line,) = lines
    assert line.origin == LineOrigin.ENTRY_FALLBACK
    assert line.amount == Decimal("800.00")
    assert line.item_name == "Cloud hosting March"
    assert line.description is None


def test_a_corrected_standin_line_survives_the_next_sync(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")
    runner.run_sync()

    (found,) = _lines(engine, tenant["company_id"])
    with Session(engine) as s:
        line = s.get(InvoiceLine, found.id)
        line.item_name = "Hetzner CX41, March"
        line.verified_fields = ["item_name"]
        s.add(line)
        s.commit()

    runner.run_sync()

    (line,) = _lines(engine, tenant["company_id"])
    assert line.item_name == "Hetzner CX41, March"


def test_an_untouched_standin_line_still_refreshes(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")
    runner.run_sync()

    scanless.entries = [
        entry("E-1", "6010", debit=800.0, description="Cloud hosting April"),
        entry("E-2", "2610", debit=200.0, description="VAT 25%"),
        entry("E-3", "8010", credit=1000.0, description="Contoso ApS"),
    ]
    runner.run_sync()

    (line,) = _lines(engine, tenant["company_id"])
    assert line.item_name == "Cloud hosting April"


def test_a_hard_reset_still_lets_the_erp_win_over_a_standin_correction(
    engine, make_tenant, scanless
):
    tenant = make_tenant("Acme")
    runner.run_sync()

    (found,) = _lines(engine, tenant["company_id"])
    line_id = found.id
    with Session(engine) as s:
        line = s.get(InvoiceLine, line_id)
        line.item_name = "Hetzner CX41, March"
        line.verified_fields = ["item_name"]
        s.add(line)
        s.commit()

    runner.run_sync(hard_reset=True)

    (line,) = _lines(engine, tenant["company_id"])
    assert line.item_name == "Cloud hosting March"
    assert "item_name" not in line.verified_fields

    with Session(engine) as s:
        rows = s.exec(
            select(AuditLog).where(
                AuditLog.entity_id == line_id, AuditLog.action == "hard_reset"
            )
        ).all()
    assert rows, "an overwrite of a human's value must stay recoverable"
    assert rows[0].actor == SYSTEM_ACTOR


def test_a_split_account_voucher_yields_a_line_per_expense_posting(
    engine, make_tenant, scanless
):
    scanless.entries = SPLIT_VOUCHER
    tenant = make_tenant("Acme")

    runner.run_sync()

    lines = _lines(engine, tenant["company_id"])
    assert [l.native_account_code for l in lines] == ["6010", "6020"]
    assert [l.amount for l in lines] == [Decimal("500.00"), Decimal("300.00")]


def test_a_credit_on_an_expense_account_is_a_negative_line(engine, make_tenant, scanless):
    scanless.entries = [
        entry("E-1", "6010", credit=800.0, description="Cloud hosting refund"),
        entry("E-2", "8010", debit=800.0, description="Contoso ApS"),
    ]
    tenant = make_tenant("Acme")

    runner.run_sync()

    (line,) = _lines(engine, tenant["company_id"])
    assert line.amount == Decimal("-800.00")


def test_a_voucher_with_no_expense_posting_yields_no_line(engine, make_tenant, scanless):
    scanless.entries = [
        entry("E-1", "8010", debit=1000.0, description="Transfer out"),
        entry("E-2", "2610", credit=1000.0, description="Transfer in"),
    ]
    tenant = make_tenant("Acme")

    runner.run_sync()

    assert _lines(engine, tenant["company_id"]) == []


def test_the_posting_links_to_the_line_it_produced(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")

    runner.run_sync()

    (line,) = _lines(engine, tenant["company_id"])
    with Session(engine) as s:
        linked = s.exec(
            select(ErpEntry).where(ErpEntry.source_invoice_line_id == line.id)
        ).all()
    assert [e.erp_entry_id for e in linked] == ["E-1"], (
        "exactly the expense posting should point at the line it stood in for"
    )


def test_the_line_is_converted_at_the_invoices_date(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")

    runner.run_sync()

    (line,) = _lines(engine, tenant["company_id"])
    assert line.base_currency is None and line.base_amount is None


def test_erp_lines_are_not_joined_by_standins(engine, make_tenant, fake_connector):
    fake_connector.accounts = TYPED_ACCOUNTS
    fake_connector.entries = BALANCED_VOUCHER
    tenant = make_tenant("Acme")

    runner.run_sync()

    lines = _lines(engine, tenant["company_id"])
    assert [l.origin for l in lines] == [LineOrigin.ERP], (
        "an invoice must hold exactly one origin — mixing them double-counts it"
    )


def test_extracted_lines_survive_a_resync(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")
    runner.run_sync()

    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        for line in s.exec(select(InvoiceLine)).all():
            s.delete(line)
        s.add(InvoiceLine(company_id=tenant["company_id"], invoice_id=invoice.id,
                          description="Dell U2724DE monitor", amount=Decimal("800.00"),
                          origin=LineOrigin.DOCUMENT_AI))
        s.commit()

    runner.run_sync()

    lines = _lines(engine, tenant["company_id"])
    assert [l.origin for l in lines] == [LineOrigin.DOCUMENT_AI]
    assert [l.description for l in lines] == ["Dell U2724DE monitor"]


def test_a_resync_does_not_duplicate_standins(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")

    runner.run_sync()
    runner.run_sync()

    lines = _lines(engine, tenant["company_id"])
    assert len(lines) == 1, f"re-sync duplicated stand-in lines: {lines}"


def test_a_resync_does_not_reset_a_categorized_standin(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")
    runner.run_sync()
    with Session(engine) as s:
        line = s.exec(select(InvoiceLine)).one()
        line.status = LineStatus.VERIFIED
        line.level_1 = "Indirect"
        s.add(line)
        s.commit()

    runner.run_sync()

    (line,) = _lines(engine, tenant["company_id"])
    assert line.status == LineStatus.VERIFIED
    assert line.level_1 == "Indirect"


def test_a_posting_added_later_gets_its_own_standin(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")
    runner.run_sync()

    scanless.entries = SPLIT_VOUCHER
    runner.run_sync()

    lines = _lines(engine, tenant["company_id"])
    assert [l.native_account_code for l in lines] == ["6010", "6020"]


def test_an_invoice_with_a_scan_is_queued(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")

    result = runner.run_sync()

    assert _invoice(engine, tenant["company_id"]).doc_status == DocStatus.PENDING
    assert result[tenant["integration_id"]]["documents_queued"] == 1


def test_an_invoice_with_no_scan_is_not_applicable(engine, make_tenant, scanless):
    scanless.scan = SCAN_WITHOUT_LINES.model_copy(
        update={"file_name": None, "file_ref": None}
    )
    tenant = make_tenant("Acme")

    result = runner.run_sync()

    invoice = _invoice(engine, tenant["company_id"])
    assert invoice.doc_status == DocStatus.NOT_APPLICABLE
    assert invoice.doc_error is None
    assert result[tenant["integration_id"]]["documents_queued"] == 0


@pytest.mark.parametrize(
    "start,expected",
    [
        (DocStatus.PROCESSED, DocStatus.PROCESSED),
        (DocStatus.PROCESSING, DocStatus.PROCESSING),
        (DocStatus.FAILED, DocStatus.FAILED),
    ],
)
def test_a_resync_leaves_a_settled_invoice_alone(
    engine, make_tenant, scanless, start, expected
):
    tenant = make_tenant("Acme")
    runner.run_sync()
    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        invoice.doc_status = start
        s.add(invoice)
        s.commit()

    result = runner.run_sync()

    assert _invoice(engine, tenant["company_id"]).doc_status == expected
    assert result[tenant["integration_id"]]["documents_queued"] == 0


def test_a_replaced_document_requeues_a_processed_invoice(engine, make_tenant, scanless):
    tenant = make_tenant("Acme")
    runner.run_sync()
    with Session(engine) as s:
        invoice = s.exec(select(Invoice)).one()
        invoice.doc_status = DocStatus.PROCESSED
        s.add(invoice)
        s.commit()

    scanless.scan = SCAN_WITHOUT_LINES.model_copy(update={"file_ref": "s3://new-scan"})
    result = runner.run_sync()

    assert _invoice(engine, tenant["company_id"]).doc_status == DocStatus.PENDING
    assert result[tenant["integration_id"]]["documents_queued"] == 1
