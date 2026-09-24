"""A line is written in the invoice's money, whatever the document printed.

Anthropic billed EUR 90.00 and Billy posted it as DKK 672.83. The extraction was
accepted — correctly, since 90.00 EUR *is* 672.83 DKK — and then
`replace_invoice_lines` wrote `amount = 90.00` onto a DKK invoice, where
`fx.convert_line` promptly treated it as 90 kroner. The ledger ended up claiming
a DKK 672.83 invoice was made of DKK 90.00 of spend.

Before the currency-aware comparison landed, a foreign-currency document could
only ever be rejected, so this could not happen. Making the comparison
cross-currency made it possible, and the storage side was not updated with it.

The rule: **one rate, one decision.** The rate that decided the extraction
reconciles is the rate its lines are stored at, so the figure judged and the
figure written can never disagree.

What is stored is a converted figure and is openly derived — a line has no
"as-posted" original, because the ERP posted a voucher with no line breakdown at
all. That is exactly why the invoice's own `currency` governs: a line that did
not agree with its invoice would break every report that sums lines and groups
by the invoice's currency column.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session, select

from ai_api.documents import runner as docs
from ai_api.documents.extractor import ExtractedLines
from ai_api.models import LineItem
from web_api.db.models import DocStatus, Invoice, InvoiceLine
from web_api.connectors.base import DocumentPayload

from ai_api_testkit import BALANCED_VOUCHER, SCAN_WITHOUT_LINES, TYPED_ACCOUNTS
from ai_api.sync import runner as sync_runner


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
    """The Anthropic failure: EUR 90.00 must not land in a DKK column as 90.00.

    The synced invoice is DKK 1000.00 gross. A document stating EUR 125.00 at a
    rate of 8 is DKK 1000.00 — it reconciles, and it must be *stored* as 1000.
    """
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
    """A rate of 1 must not perturb the figure — no rounding drift on the
    ordinary case, which is nearly every document."""
    monkeypatch.setattr(docs, "FxService", lambda session: _Rates({}))

    def _extract(payload):
        return ExtractedLines(
            lines=[LineItem(description="Widget", amount=1000.0)], currency="DKK"
        )

    docs.run_documents(extract=_extract)

    (line,) = _lines(engine)
    assert line.amount == Decimal("1000.00")


def test_a_document_naming_no_currency_is_taken_as_the_invoices(engine, synced, monkeypatch):
    """Most receipts print no ISO code. Assuming a mismatch would reject them
    all; assuming the invoice's is the only reading that lets them through."""
    monkeypatch.setattr(docs, "FxService", lambda session: _Rates({}))

    def _extract(payload):
        return ExtractedLines(lines=[LineItem(description="Widget", amount=1000.0)])

    docs.run_documents(extract=_extract)

    (line,) = _lines(engine)
    assert line.amount == Decimal("1000.00")


def test_the_unit_price_is_converted_with_the_amount(engine, synced, monkeypatch):
    """A converted amount beside an unconverted unit price is a line that
    contradicts itself on the page a reviewer reads."""
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
    """Refusing beats writing a foreign figure into a local column."""
    monkeypatch.setattr(docs, "FxService", lambda session: _Rates({}))

    def _extract(payload):
        return ExtractedLines(
            lines=[LineItem(description="Claude Max", amount=125.0)], currency="EUR"
        )

    counts = docs.run_documents(extract=_extract)

    assert counts["rejected"] == 1
    assert _invoice(engine).doc_status == DocStatus.FAILED
    assert "EUR" in _invoice(engine).doc_error
