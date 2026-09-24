"""What a re-sync may and may not overwrite once a human has spoken.

Corrections are applied in place, over the ERP's own value, so nothing but the
row's `verified_fields` stands between a human's work and the next run of a
process that reassigns those very columns. These are the tests for that.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from ai_api.sync import runner
from web_api.db.models import AuditLog, Invoice, InvoiceLine, LineOrigin, LineStatus

from ai_api_testkit import INVOICE


@pytest.fixture
def synced(engine, make_tenant):
    """One tenant, synced once — the state a reviewer would find."""
    tenant = make_tenant("Acme")
    runner.run_sync()
    with Session(engine) as s:
        invoice = s.exec(
            select(Invoice).where(Invoice.company_id == tenant["company_id"])
        ).one()
        return {**tenant, "invoice_id": invoice.id}


def _restate(**changes):
    """Script the ERP to restate the invoice with different figures."""
    from ai_api_testkit import FakeConnector

    FakeConnector.scan = INVOICE.model_copy(update=changes)


def _verify(engine, invoice_id: str, **fields):
    """Apply a human's correction the way the API would: value plus the mark."""
    with Session(engine) as s:
        invoice = s.get(Invoice, invoice_id)
        for field, value in fields.items():
            setattr(invoice, field, value)
        invoice.verified_fields = sorted(fields)
        invoice.verified_by = "user-1"
        s.add(invoice)
        s.commit()


def _invoice(engine, invoice_id: str) -> Invoice:
    with Session(engine) as s:
        return s.get(Invoice, invoice_id)


# -- The ordinary run ----------------------------------------------------------


def test_a_verified_total_survives_a_re_sync(engine, synced):
    _verify(engine, synced["invoice_id"], total=Decimal("1234.00"))
    _restate(total=1000.0)

    runner.run_sync()

    assert _invoice(engine, synced["invoice_id"]).total == Decimal("1234.00")


def test_an_unverified_field_is_still_refreshed(engine, synced):
    """Per field, not per row. A reviewer who settled the total has said nothing
    about the date, and a genuine later re-posting of it must still reach us."""
    _verify(engine, synced["invoice_id"], total=Decimal("1234.00"))
    _restate(total=1000.0, invoice_date=date(2026, 4, 15))

    runner.run_sync()

    invoice = _invoice(engine, synced["invoice_id"])
    assert invoice.total == Decimal("1234.00")
    assert invoice.invoice_date == date(2026, 4, 15)


def test_a_verified_line_field_survives_a_re_sync(engine, synced):
    with Session(engine) as s:
        line = s.exec(
            select(InvoiceLine).where(InvoiceLine.invoice_id == synced["invoice_id"])
        ).one()
        line.description = "Dell U2724DE monitor"
        line.verified_fields = ["description"]
        s.add(line)
        s.commit()
        line_id = line.id

    runner.run_sync()

    with Session(engine) as s:
        line = s.get(InvoiceLine, line_id)
        assert line.description == "Dell U2724DE monitor"
        # The ERP still restates everything nobody settled.
        assert line.amount == Decimal("800.00")


def test_a_human_line_survives_a_re_sync(engine, synced):
    """The connector has no statement about a line it did not produce, and the
    ids it derives cannot collide with a human line's fresh UUID."""
    with Session(engine) as s:
        line = InvoiceLine(
            company_id=synced["company_id"], invoice_id=synced["invoice_id"],
            description="Freight", amount=Decimal("40.00"),
            origin=LineOrigin.HUMAN, status=LineStatus.UNCATEGORIZED, sequence=9,
        )
        s.add(line)
        s.commit()
        line_id = line.id

    runner.run_sync()

    with Session(engine) as s:
        line = s.get(InvoiceLine, line_id)
        assert line is not None
        assert line.description == "Freight"
        assert line.origin == LineOrigin.HUMAN


# -- The escape hatch ----------------------------------------------------------


def test_hard_reset_restores_the_erps_value_and_audits_it(engine, synced):
    _verify(engine, synced["invoice_id"], total=Decimal("1234.00"))
    _restate(total=1000.0)

    runner.run_sync(hard_reset=True)

    invoice = _invoice(engine, synced["invoice_id"])
    assert invoice.total == Decimal("1000.00")
    # The row must not go on claiming a field is verified at a value it no
    # longer holds.
    assert invoice.verified_fields == []

    with Session(engine) as s:
        rows = s.exec(
            select(AuditLog).where(
                AuditLog.entity_type == "invoice",
                AuditLog.entity_id == synced["invoice_id"],
            )
        ).all()
    assert [r.action for r in rows] == ["hard_reset"]
    # Attributed to the system, and carrying the human's value — the only place
    # it survives, exactly as the ERP's does after an ordinary correction.
    assert rows[0].actor == "system"
    (change,) = rows[0].changes
    assert change["field"] == "total"
    # Compared as numbers: the entry records the value at assignment time, whose
    # scale is the connector's ("1000.0"), not the column's after a round-trip.
    assert Decimal(change["old"]) == Decimal("1234.00")
    assert Decimal(change["new"]) == Decimal("1000.00")


def test_hard_reset_is_never_implied_by_another_flag(engine, synced):
    _verify(engine, synced["invoice_id"], total=Decimal("1234.00"))
    _restate(total=1000.0)

    runner.run_sync(since=date(2020, 1, 1), integration_id=synced["integration_id"])

    assert _invoice(engine, synced["invoice_id"]).total == Decimal("1234.00")


def test_hard_reset_does_not_delete_human_lines(engine, synced):
    """It restores values; it is not a "drop everything the customer did" button.
    Removing a human line is a delete the customer performs themselves."""
    with Session(engine) as s:
        line = InvoiceLine(
            company_id=synced["company_id"], invoice_id=synced["invoice_id"],
            description="Freight", origin=LineOrigin.HUMAN,
            status=LineStatus.UNCATEGORIZED, sequence=9,
        )
        s.add(line)
        s.commit()
        line_id = line.id

    runner.run_sync(hard_reset=True)

    with Session(engine) as s:
        assert s.get(InvoiceLine, line_id) is not None


# -- Document queueing ---------------------------------------------------------


def test_a_new_document_does_not_requeue_an_invoice_with_verified_lines(engine, synced):
    """Extraction replaces an invoice's lines wholly, so queueing here would
    discard a person's work on the strength of a document nobody asked us to
    re-read."""
    with Session(engine) as s:
        invoice = s.get(Invoice, synced["invoice_id"])
        invoice.doc_status = "processed"
        s.add(invoice)
        line = s.exec(
            select(InvoiceLine).where(InvoiceLine.invoice_id == synced["invoice_id"])
        ).one()
        line.status = LineStatus.VERIFIED
        s.add(line)
        s.commit()

    _restate(file_name="a-different-scan.pdf")
    runner.run_sync()

    assert _invoice(engine, synced["invoice_id"]).doc_status == "processed"


def test_a_new_document_still_requeues_an_untouched_invoice(engine, synced):
    with Session(engine) as s:
        invoice = s.get(Invoice, synced["invoice_id"])
        invoice.doc_status = "processed"
        s.add(invoice)
        s.commit()

    _restate(file_name="a-different-scan.pdf")
    runner.run_sync()

    assert _invoice(engine, synced["invoice_id"]).doc_status == "pending"
