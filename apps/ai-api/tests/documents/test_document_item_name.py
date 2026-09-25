"""What was bought, named — and the prose about it, kept apart."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session, select

from ai_api.documents import runner as docs
from ai_api.documents.content import ExtractedLines
from ai_api.documents.replace import _name_and_description
from ai_api.models import LineItem
from ai_api.sync import runner as sync_runner
from ai_api_testkit import BALANCED_VOUCHER, SCAN_WITHOUT_LINES, TYPED_ACCOUNTS
from web_api.connectors.base import DocumentPayload
from web_api.db.models import AuditLog, InvoiceLine


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


def _lines(engine) -> list[InvoiceLine]:
    with Session(engine) as s:
        return list(s.exec(select(InvoiceLine)).all())


def _extracting(*items):
    """A stub extractor returning exactly these lines, in the invoice's money."""
    def _extract(payload):
        return ExtractedLines(lines=list(items), currency="DKK")
    return _extract


def test_a_line_stating_both_keeps_both():
    item = LineItem(item_name="Figma Organization seat", description="Annual, 12 seats")
    assert _name_and_description(item) == ("Figma Organization seat", "Annual, 12 seats")


def test_a_line_stating_one_text_has_named_the_item():
    assert _name_and_description(LineItem(description="Cloudflare Pro")) == (
        "Cloudflare Pro", None,
    )


def test_a_model_echoing_the_name_into_both_states_one_text():
    item = LineItem(item_name="Consulting", description="Consulting")
    assert _name_and_description(item) == ("Consulting", None)


def test_an_unreadable_line_names_nothing():
    assert _name_and_description(LineItem()) == (None, None)


def test_whitespace_is_not_a_value():
    item = LineItem(item_name="  Figma seat  ", description="   ")
    assert _name_and_description(item) == ("Figma seat", None)


def test_an_extraction_stating_both_stores_both(engine, synced):
    counts = docs.run_documents(
        extract=_extracting(
            LineItem(item_name="Figma Organization seat",
                     description="Annual plan, billed yearly", amount=1000.0)
        )
    )

    assert counts["processed"] == 1
    (line,) = _lines(engine)
    assert line.item_name == "Figma Organization seat"
    assert line.description == "Annual plan, billed yearly"


def test_an_extraction_stating_one_text_stores_it_as_the_name(engine, synced):
    docs.run_documents(
        extract=_extracting(LineItem(description="Cloudflare Pro", amount=1000.0))
    )

    (line,) = _lines(engine)
    assert line.item_name == "Cloudflare Pro"
    assert line.description is None


def test_replacement_audits_the_item_name_it_removed(engine, synced):
    with Session(engine) as s:
        line = s.exec(select(InvoiceLine)).one()
        line.item_name = "Stand-in: Edb-udgifter"
        s.add(line)
        s.commit()
        replaced_id = line.id

    docs.run_documents(
        extract=_extracting(LineItem(item_name="Figma seat", amount=1000.0))
    )

    with Session(engine) as s:
        row = s.exec(
            select(AuditLog).where(
                AuditLog.entity_id == replaced_id,
                AuditLog.action == "superseded_by_extraction",
            )
        ).one()

    assert {"field": "item_name", "old": "Stand-in: Edb-udgifter", "new": None} in row.changes


def test_the_replacing_line_is_still_stored_in_the_invoices_money(engine, synced):
    docs.run_documents(
        extract=_extracting(
            LineItem(item_name="Figma seat", description="12 seats", amount=1000.0)
        )
    )

    (line,) = _lines(engine)
    assert line.amount == Decimal("1000.00")
