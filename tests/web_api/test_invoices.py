"""Invoice management tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlmodel import Session

from web_api.db.models import Invoice

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
