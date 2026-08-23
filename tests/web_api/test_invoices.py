"""Invoice management tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from web_api.db.models import AuditLog, Invoice, Vendor

from .conftest import auth


def _link_vendor(engine, invoice_id: str, **fields) -> str:
    """Give an invoice a supplier from the global catalog, and return its id."""
    with Session(engine) as s:
        vendor = Vendor(name=fields.pop("name", "Nordic Supplies ApS"), **fields)
        s.add(vendor)
        s.commit()
        inv = s.get(Invoice, invoice_id)
        inv.vendor_id = vendor.id
        s.add(inv)
        s.commit()
        return vendor.id


def test_invoice_read_exposes_erp_provenance_by_default(client, seed):
    res = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA"))
    assert res.status_code == 200
    # Sync-created invoices report ERP provenance. It tells a reviewer how much
    # to trust the values; it no longer decides whether they may be corrected.
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


def test_patch_corrects_an_erp_sourced_invoice(client, seed):
    """Provenance no longer gates correction.

    It used to: a non-`pdf_extraction` invoice was refused with a 409 on the
    grounds that ERP-posted values are evidence. But nothing in production ever
    set `pdf_extraction`, so the refusal covered *every* real invoice — and a
    bookkeeper's posting can be as wrong as an extraction. What protects a
    correction from the next sync is now `verified_fields`, and what keeps the
    ERP's own figure recoverable is the audit entry.
    """
    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"invoice_number": "CORRECTED"}, headers=auth("tokA"))

    assert res.status_code == 200
    assert res.json()["invoice_number"] == "CORRECTED"


def test_patch_corrects_a_parsed_invoice_and_audits_it(client, seed, engine):
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
    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"invoice_number": "A1"}, headers=auth("tokA"))
    assert res.status_code == 200

    with Session(engine) as s:
        rows = s.exec(select(AuditLog).where(AuditLog.entity_type == "invoice")).all()
    assert len(rows) == 1
    assert rows[0].action == "noop"
    assert rows[0].changes == []


def test_patch_correcting_total_clears_stale_base_amounts(client, seed, engine):
    """The base/FX columns were derived from the pre-correction total. Once the
    total changes, those derived figures no longer describe anything real and
    must not be left in place pretending they still do."""
    with Session(engine) as s:
        # Seeded with base_currency=DKK, base_total=100.00, fx_rate=1 — confirm
        # the fixture actually gives us something to clear.
        assert s.get(Invoice, seed["inv_a"]).base_total == Decimal("100.00")

    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"total": "150.00"}, headers=auth("tokA"))
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == "150.00"
    assert body["base_currency"] is None
    assert body["base_total"] is None
    assert body["base_tax"] is None
    assert body["fx_rate"] is None
    assert body["fx_rate_date"] is None

    with Session(engine) as s:
        inv = s.get(Invoice, seed["inv_a"])
        assert inv.base_total is None
        assert inv.fx_rate is None


def test_patch_correcting_only_invoice_number_leaves_base_amounts_intact(client, seed, engine):
    """A correction that never touches currency/total/tax has no effect on the
    stored conversion — it must not be cleared as a side effect of an
    unrelated field edit."""
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
        inv = s.get(Invoice, seed["inv_a"])
        assert inv.base_currency == "DKK"
        assert inv.base_total == Decimal("100.00")
        assert inv.fx_rate == Decimal("1")
        assert inv.fx_rate_date == date(2025, 7, 1)


# -- The number printed on the document ----------------------------------------


def _audit_rows(engine, invoice_id: str) -> list[AuditLog]:
    with Session(engine) as s:
        return s.exec(
            select(AuditLog)
            .where(AuditLog.entity_type == "invoice", AuditLog.entity_id == invoice_id)
            .order_by(AuditLog.created_at, AuditLog.id)
        ).all()


def test_patch_corrects_the_printed_number_and_audits_what_was_read(client, seed, engine):
    """A model read this off a scan and may have misread a digit. The correction
    is applied in place, so the audit row is the only record of the reading."""
    with Session(engine) as s:
        inv = s.get(Invoice, seed["inv_a"])
        inv.document_invoice_number = "2026-04I2"
        s.add(inv)
        s.commit()

    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"document_invoice_number": "2026-0412"}, headers=auth("tokA"))

    assert res.status_code == 200
    assert res.json()["document_invoice_number"] == "2026-0412"

    rows = _audit_rows(engine, seed["inv_a"])
    assert [r.action for r in rows] == ["edit"]
    assert {"field": "document_invoice_number", "old": "2026-04I2",
            "new": "2026-0412"} in rows[0].changes


def test_correcting_the_printed_number_leaves_the_posted_one_alone(client, seed, engine):
    """The as-posted value is the ledger's own record. Billy's often falls back
    to the bill id, and that fact is evidence, not something to overwrite."""
    client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                 json={"document_invoice_number": "2026-0412"}, headers=auth("tokA"))

    with Session(engine) as s:
        assert s.get(Invoice, seed["inv_a"]).invoice_number == "A1"


def test_correcting_the_printed_number_leaves_the_conversion_intact(client, seed, engine):
    """An invoice number is not an input to any conversion, so unlike
    currency/total/tax it must not clear the base figures."""
    client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                 json={"document_invoice_number": "2026-0412"}, headers=auth("tokA"))

    with Session(engine) as s:
        inv = s.get(Invoice, seed["inv_a"])
        assert inv.base_currency == "DKK"
        assert inv.base_total == Decimal("100.00")
        assert inv.fx_rate == Decimal("1")
        assert inv.fx_rate_date == date(2025, 7, 1)


def test_verify_settles_the_printed_number(client, seed, engine):
    """Resubmitting the value a model read is a human asserting that figure —
    which is the label the extractor learns from."""
    with Session(engine) as s:
        inv = s.get(Invoice, seed["inv_a"])
        inv.document_invoice_number = "2026-0412"
        s.add(inv)
        s.commit()

    body = client.post(f"/api/v1/invoices/{seed['inv_a']}/verify",
                       json={"document_invoice_number": "2026-0412"},
                       headers=auth("tokA")).json()

    assert "document_invoice_number" in body["verified_fields"]


# -- Supplier: an invoice-scoped override, never a write to the shared catalog --


def test_supplier_resolves_from_the_vendor_when_not_overridden(client, seed, engine):
    _link_vendor(engine, seed["inv_a"], country_code="DK", vat_number="DK12345678")

    body = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA")).json()

    assert body["supplier_name"] == "Nordic Supplies ApS"
    assert body["supplier_country_code"] == "DK"
    assert body["supplier_vat_number"] == "DK12345678"
    assert body["supplier_overrides"] == []


def test_supplier_override_does_not_touch_the_global_vendor(client, seed, engine):
    """`Vendor` is a global catalog shared across organizations. A correction
    written through to it would silently rewrite the supplier for every other
    tenant — which is why the override lives on the invoice."""
    vendor_id = _link_vendor(engine, seed["inv_a"], country_code="DK")

    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"supplier_country_code": "DE"}, headers=auth("tokA"))
    assert res.status_code == 200

    body = res.json()
    assert body["supplier_country_code"] == "DE"
    assert body["supplier_overrides"] == ["supplier_country_code"]
    # The name still falls back to the catalog: an override is per field.
    assert body["supplier_name"] == "Nordic Supplies ApS"

    with Session(engine) as s:
        assert s.get(Vendor, vendor_id).country_code == "DK"


def test_repointing_the_vendor_changes_which_supplier_is_reported(client, seed, engine):
    _link_vendor(engine, seed["inv_a"], country_code="DK")
    with Session(engine) as s:
        other = Vendor(name="Berlin Werkzeug GmbH", country_code="DE")
        s.add(other)
        s.commit()
        other_id = other.id

    body = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                        json={"vendor_id": other_id}, headers=auth("tokA")).json()

    assert body["vendor_id"] == other_id
    assert body["supplier_name"] == "Berlin Werkzeug GmbH"
    assert body["supplier_country_code"] == "DE"


def test_an_unknown_vendor_is_422_and_writes_nothing(client, seed, engine):
    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"vendor_id": "no-such-vendor", "invoice_number": "X"},
                       headers=auth("tokA"))

    assert res.status_code == 422
    with Session(engine) as s:
        inv = s.get(Invoice, seed["inv_a"])
        # The whole request is refused, not partly applied: the invoice number
        # sent alongside must not have landed.
        assert inv.vendor_id is None
        assert inv.invoice_number == "A1"
        assert s.exec(select(AuditLog).where(AuditLog.entity_type == "invoice")).all() == []


# -- Verification: the label, distinct from the correction ---------------------


def test_verify_with_no_body_accepts_the_parse(client, seed, engine):
    """"I looked, and it was right" is a signal a PATCH cannot express, and the
    most valuable one this endpoint collects."""
    res = client.post(f"/api/v1/invoices/{seed['inv_a']}/verify", headers=auth("tokA"))

    assert res.status_code == 200
    body = res.json()
    assert body["verified_at"] is not None
    # Nothing was asserted about any particular field, so nothing is settled.
    assert body["verified_fields"] == []

    with Session(engine) as s:
        rows = s.exec(select(AuditLog).where(AuditLog.entity_type == "invoice")).all()
    assert [r.action for r in rows] == ["verify"]
    # Attributed to the acting user, never to `system`: an automated write is
    # not a verification. The same id the audit entry names.
    assert body["verified_by"] == rows[0].actor
    assert body["verified_by"] != "system"


def test_verify_with_a_correction_is_an_edit_and_marks_the_field(client, seed, engine):
    res = client.post(f"/api/v1/invoices/{seed['inv_a']}/verify",
                      json={"tax": "25.00"}, headers=auth("tokA"))

    assert res.status_code == 200
    body = res.json()
    assert body["tax"] == "25.00"
    assert body["verified_fields"] == ["tax"]

    with Session(engine) as s:
        rows = s.exec(select(AuditLog).where(AuditLog.entity_type == "invoice")).all()
    assert [r.action for r in rows] == ["edit"]
    assert any(c["field"] == "tax" and c["old"] is None for c in rows[0].changes)


def test_verifying_an_unchanged_value_still_settles_the_field(client, seed, engine):
    """Resubmitting the stored value is a human asserting that figure is right.

    The field is settled even though no value moved — which is the whole point:
    that assertion is what stops the next sync overwriting it. The audit action
    is `verify` rather than `edit`, because a verification did happen and
    nothing was corrected; `noop` is the *PATCH* vocabulary for "you asked me to
    change something and nothing changed", which is not what this was.
    """
    res = client.post(f"/api/v1/invoices/{seed['inv_a']}/verify",
                      json={"invoice_number": "A1"}, headers=auth("tokA"))

    assert res.status_code == 200
    assert res.json()["verified_fields"] == ["invoice_number"]

    with Session(engine) as s:
        rows = s.exec(select(AuditLog).where(AuditLog.entity_type == "invoice")).all()
    assert [r.action for r in rows] == ["verify"]
    assert rows[0].changes == []


def test_verifying_twice_keeps_what_was_settled_before(client, seed):
    client.post(f"/api/v1/invoices/{seed['inv_a']}/verify",
                json={"total": "100.00"}, headers=auth("tokA"))
    body = client.post(f"/api/v1/invoices/{seed['inv_a']}/verify",
                       json={"tax": "25.00"}, headers=auth("tokA")).json()

    assert body["verified_fields"] == ["tax", "total"]


def test_verify_requires_management(client, seed):
    res = client.post(f"/api/v1/invoices/{seed['inv_a']}/verify", headers=auth("tok_viewerA"))
    assert res.status_code == 403


def test_verify_a_foreign_invoice_is_404(client, seed, engine):
    res = client.post(f"/api/v1/invoices/{seed['inv_b']}/verify", headers=auth("tokA"))

    assert res.status_code == 404
    with Session(engine) as s:
        assert s.get(Invoice, seed["inv_b"]).verified_at is None


# -- Reconciliation: reported on the detail, never enforced --------------------


def test_lines_summing_to_the_total_reconcile(client, seed):
    """The seed's two lines are 80 + 20 against a total of 100."""
    body = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA")).json()

    assert body["lines_reconciled"] is True
    assert body["reconciliation_delta"] is None


def test_a_correction_that_breaks_reconciliation_is_saved_and_reported(client, seed):
    """Warned, never blocked: a reviewer part-way through a multi-line fix must
    not be blocked by their own unfinished work."""
    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"total": "500.00"}, headers=auth("tokA"))
    assert res.status_code == 200

    body = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA")).json()
    assert body["lines_reconciled"] is False
    # Signed, so a reader can see which way it is out: the lines are 400 short.
    assert Decimal(body["reconciliation_delta"]) == Decimal("-400.00")
