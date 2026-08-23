"""What was bought, named — and the prose about it, kept apart.

An invoice line had exactly one free-text field, and it was doing two jobs. A
document states a product ("Figma Organization seat") and, sometimes, prose
about it ("Annual plan, billed yearly"). Collapsed into one column, the name is
only ever recoverable by reading a sentence — which is the work this product
exists to remove.

The split is decided by `_name_and_description`, a pure function, rather than by
the model's discipline. Asking a small local model for two texts where the
document prints one is an invitation to manufacture the second, and an invented
description is worse than an absent one. So the prompt states the fallback and
the code enforces it.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session, select

from ai_api.documents import runner as docs
from ai_api.documents.extractor import ExtractedLines
from ai_api.documents.replace import _name_and_description
from ai_api.models import LineItem
from web_api.db.models import AuditLog, InvoiceLine
from web_api.connectors.base import DocumentPayload

from .test_sync_standin_lines import BALANCED_VOUCHER, SCAN_WITHOUT_LINES, TYPED_ACCOUNTS
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


def _lines(engine) -> list[InvoiceLine]:
    with Session(engine) as s:
        return list(s.exec(select(InvoiceLine)).all())


def _extracting(*items):
    """A stub extractor returning exactly these lines, in the invoice's money."""
    def _extract(payload):
        return ExtractedLines(lines=list(items), currency="DKK")
    return _extract


# -- The split rule, in isolation ----------------------------------------------


def test_a_line_stating_both_keeps_both():
    item = LineItem(item_name="Figma Organization seat", description="Annual, 12 seats")
    assert _name_and_description(item) == ("Figma Organization seat", "Annual, 12 seats")


def test_a_line_stating_one_text_has_named_the_item():
    """Most receipt lines print one text. Filing it under `description` would
    leave the always-present field empty on the documents that read cleanly."""
    assert _name_and_description(LineItem(description="Cloudflare Pro")) == (
        "Cloudflare Pro", None,
    )


def test_a_model_echoing_the_name_into_both_states_one_text():
    """Models repeat. Storing the same string twice makes the split meaningless
    on the day it was introduced."""
    item = LineItem(item_name="Consulting", description="Consulting")
    assert _name_and_description(item) == ("Consulting", None)


def test_an_unreadable_line_names_nothing():
    """Null, never a guess — the same rule an unreadable amount follows."""
    assert _name_and_description(LineItem()) == (None, None)


def test_whitespace_is_not_a_value():
    item = LineItem(item_name="  Figma seat  ", description="   ")
    assert _name_and_description(item) == ("Figma seat", None)


# -- Through the stage ---------------------------------------------------------


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
    """The audit row is the only record a superseded line's values existed.
    A name omitted from it is a name destroyed with nothing to notice."""
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
    """A guard on the split: naming a line must not disturb what it costs."""
    docs.run_documents(
        extract=_extracting(
            LineItem(item_name="Figma seat", description="12 seats", amount=1000.0)
        )
    )

    (line,) = _lines(engine)
    assert line.amount == Decimal("1000.00")
