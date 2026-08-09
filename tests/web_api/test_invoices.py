"""Invoice management tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from web_api.db.models import AuditLog, Invoice

from .conftest import auth


def test_invoice_read_exposes_erp_provenance_by_default(client, seed):
    res = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA"))
    assert res.status_code == 200
    # Sync-created invoices are ERP evidence: their header is not correctable.
    assert res.json()["source"] == "erp"


def test_invoice_read_returns_non_default_source_from_database(client, seed, engine):
    """Verify source round-trips through the database.

    If the ORM field were missing, Pydantic would still return the schema default "erp".
    This test uses a non-default value to prove the field actually persists and retrieves.
    """
    # Create an AI-parsed invoice with source="pdf_extraction" directly in the database.
    with Session(engine) as s:
        inv_ai = Invoice(
            company_id=seed["comp_a"],
            invoice_number="AI1",
            invoice_date=date(2025, 8, 15),
            currency="DKK",
            total=Decimal("200.00"),
            status="uncategorized",
            base_currency="DKK",
            base_total=Decimal("200.00"),
            fx_rate=Decimal("1"),
            fx_rate_date=date(2025, 8, 15),
            source="pdf_extraction",  # Non-default value proves round-trip
        )
        s.add(inv_ai)
        s.commit()
        inv_id = inv_ai.id

    # Fetch via API and verify the non-default value is returned.
    res = client.get(f"/api/v1/invoices/{inv_id}", headers=auth("tokA"))
    assert res.status_code == 200
    assert res.json()["source"] == "pdf_extraction"


def test_patch_rejects_an_erp_sourced_invoice(client, seed):
    """The as-posted ERP columns are evidence. The rule is enforced by the API,
    not only by the UI declining to render an input."""
    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"invoice_number": "TAMPERED"}, headers=auth("tokA"))

    assert res.status_code == 409
    assert "erp" in res.json()["detail"].lower()


def test_patch_corrects_a_parsed_invoice_and_audits_it(client, seed, engine):
    with Session(engine) as s:
        inv = s.get(Invoice, seed["inv_a"])
        inv.source = "pdf_extraction"
        s.add(inv)
        s.commit()

    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"invoice_number": "INV-9"}, headers=auth("tokA"))

    assert res.status_code == 200
    assert res.json()["invoice_number"] == "INV-9"

    with Session(engine) as s:
        rows = s.exec(select(AuditLog).where(AuditLog.entity_type == "invoice")).all()
    assert len(rows) == 1
    assert rows[0].action == "edit"


def test_patch_requires_management(client, seed):
    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"invoice_number": "X"}, headers=auth("tok_viewerA"))
    assert res.status_code == 403


def test_patch_a_foreign_invoice_is_404_not_403(client, seed):
    """A cross-tenant invoice must be indistinguishable from a missing one."""
    res = client.patch(f"/api/v1/invoices/{seed['inv_b']}",
                       json={"invoice_number": "X"}, headers=auth("tokA"))
    assert res.status_code == 404


def test_patch_missing_invoice_is_404(client, seed):
    res = client.patch("/api/v1/invoices/does-not-exist",
                       json={"invoice_number": "X"}, headers=auth("tokA"))
    assert res.status_code == 404


def test_patch_with_no_actual_change_records_a_noop_not_an_edit(client, seed, engine):
    """A PATCH that resubmits the same value changes nothing on the row, and
    the audit trail should say so rather than claiming a correction happened."""
    with Session(engine) as s:
        inv = s.get(Invoice, seed["inv_a"])
        inv.source = "pdf_extraction"
        s.add(inv)
        s.commit()

    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"invoice_number": "A1"}, headers=auth("tokA"))
    assert res.status_code == 200

    with Session(engine) as s:
        rows = s.exec(select(AuditLog).where(AuditLog.entity_type == "invoice")).all()
    assert len(rows) == 1
    assert rows[0].action == "noop"
    assert rows[0].changes == []
