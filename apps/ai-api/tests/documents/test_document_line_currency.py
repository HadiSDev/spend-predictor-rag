"""A line is written in the invoice's money, whatever the document printed."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session, select

from ai_api.documents import runner as docs
from ai_api.documents.content import ExtractedLines
from ai_api.models import LineItem
from ai_api.sync import runner as sync_runner
from ai_api_testkit import BALANCED_VOUCHER, SCAN_WITHOUT_LINES, TYPED_ACCOUNTS
from web_api.connectors.base import DocumentPayload
from web_api.db.models import DocStatus, Invoice, InvoiceLine


@pytest.fixture(autouse=True)
def _stage_engine(engine, monkeypatch):
    monkeypatch.setattr(docs, "engine", engine)
    return engine


@pytest.fixture
def synced(engine, fake_connector, make_tenant):
    fake_connector.accounts = TYPED_ACCOUNTS
    fake_connector.entries = BALANCED_VOUCHER
    fake_connector.scan = SCAN_WITHOUT_LINES
    tenant = make_tenant("Acme")
    sync_runner.run_sync()
    return tenant


@pytest.fixture(autouse=True)
def _serves_a_document(fake_connector, monkeypatch):
    monkeypatch.setattr(
        fake_connector, "fetch_invoice_document",
        lambda self, voucher_id: DocumentPayload(
            content=b"%PDF-1.4 fake", media_type="application/pdf", filename="inv-1.pdf"
        ),
        raising=False,
    )


class _Rates:
    """A stub with `FxService.get_rate`'s shape, so no network is touched."""

    def __init__(self, table):
        self.table = table

    def get_rate(self, source, target, on_date):
        if on_date is None:
            return None
        rate = self.table.get((source, target))
        return (Decimal(rate), on_date) if rate else None


def _lines(engine) -> list[InvoiceLine]:
    with Session(engine) as s:
        return list(s.exec(select(InvoiceLine)).all())


def _invoice(engine) -> Invoice:
    with Session(engine) as s:
        return s.exec(select(Invoice)).one()


def test_a_foreign_currency_line_is_stored_in_the_invoices_currency(
    engine, synced, monkeypatch
):
    monkeypatch.setattr(docs, "FxService", lambda session: _Rates({("EUR", "DKK"): "8"}))

    def _extract(payload):
        return ExtractedLines(
            lines=[LineItem(description="Claude Max", amount=125.0)],
            currency="EUR",
        )

    counts = docs.run_documents(extract=_extract)

    assert counts["processed"] == 1
    (line,) = _lines(engine)
    assert line.amount == Decimal("1000.00"), (
        "the line must be in the invoice's money, not the document's"
    )


def test_a_same_currency_line_is_stored_exactly_as_the_document_printed_it(
    engine, synced, monkeypatch
):
    monkeypatch.setattr(docs, "FxService", lambda session: _Rates({}))

    def _extract(payload):
        return ExtractedLines(
            lines=[LineItem(description="Widget", amount=1000.0)], currency="DKK"
        )

    docs.run_documents(extract=_extract)

    (line,) = _lines(engine)
    assert line.amount == Decimal("1000.00")


def test_a_document_naming_no_currency_is_taken_as_the_invoices(engine, synced, monkeypatch):
    monkeypatch.setattr(docs, "FxService", lambda session: _Rates({}))

    def _extract(payload):
        return ExtractedLines(lines=[LineItem(description="Widget", amount=1000.0)])

    docs.run_documents(extract=_extract)

    (line,) = _lines(engine)
    assert line.amount == Decimal("1000.00")


def test_the_unit_price_is_converted_with_the_amount(engine, synced, monkeypatch):
    monkeypatch.setattr(docs, "FxService", lambda session: _Rates({("EUR", "DKK"): "8"}))

    def _extract(payload):
        return ExtractedLines(
            lines=[LineItem(description="Claude Max", quantity=5.0,
                            unit_price=25.0, amount=125.0)],
            currency="EUR",
        )

    docs.run_documents(extract=_extract)

    (line,) = _lines(engine)
    assert line.amount == Decimal("1000.00")
    assert line.unit_price == Decimal("200.00")
    assert line.quantity == Decimal("5"), "a count is not money and never converts"


def test_a_cross_currency_document_with_no_rate_is_rejected_not_stored_raw(
    engine, synced, monkeypatch
):
    monkeypatch.setattr(docs, "FxService", lambda session: _Rates({}))

    def _extract(payload):
        return ExtractedLines(
            lines=[LineItem(description="Claude Max", amount=125.0)], currency="EUR"
        )

    counts = docs.run_documents(extract=_extract)

    assert counts["rejected"] == 1
    assert _invoice(engine).doc_status == DocStatus.FAILED
    assert "EUR" in _invoice(engine).doc_error
