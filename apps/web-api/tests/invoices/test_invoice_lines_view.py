"""The line-level API: voucher payloads carry lines, and lines can be filtered."""
from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from web_api.db.models import (
    AuditLog,
    DocStatus,
    ErpEntry,
    Invoice,
    InvoiceLine,
    LineOrigin,
    User,
    Vendor,
)
from web_api_testkit import auth


def test_a_voucher_group_carries_its_invoice_lines(client, voucher_seed):
    r = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"))
    assert r.status_code == 200

    group = next(g for g in r.json()["items"] if g["voucher_id"] == "4821")
    assert [l["description"] for l in group["lines"]] == ["Cloud server", "Support"]
    assert {l["origin"] for l in group["lines"]} == {"erp"}


def test_lines_read_in_the_order_their_source_stated_them(client, voucher_seed, engine):
    with Session(engine) as s:
        for line in s.exec(select(InvoiceLine)).all():
            if line.description == "Support":
                line.sequence = 0
            elif line.description == "Cloud server":
                line.sequence = 1
            s.add(line)
        s.commit()

    r = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"))

    group = next(g for g in r.json()["items"] if g["voucher_id"] == "4821")
    assert [l["description"] for l in group["lines"]] == ["Support", "Cloud server"]


def test_a_lines_categorization_travels_with_it(client, voucher_seed):
    r = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"))

    group = next(g for g in r.json()["items"] if g["voucher_id"] == "4821")
    support = next(l for l in group["lines"] if l["description"] == "Support")
    assert support["level_2"] == "Technology"
    assert support["status"] == "ai_categorized"
    assert support["base_amount"] == "20.00"


def test_processing_state_travels_with_the_voucher(client, voucher_seed, engine):
    with Session(engine) as s:
        invoice = s.get(Invoice, voucher_seed["inv_a"])
        invoice.doc_status = DocStatus.FAILED
        invoice.doc_error = "inv-1.jpg: no extractor for media type 'image/jpeg'"
        s.add(invoice)
        s.commit()

    r = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"))

    group = next(g for g in r.json()["items"] if g["voucher_id"] == "4821")
    assert group["doc_status"] == "failed"
    assert "image/jpeg" in group["doc_error"]


def test_a_voucher_with_no_invoice_has_no_lines(client, voucher_seed):
    r = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"))
    assert r.status_code == 200

    lone = next(
        g for g in r.json()["items"]
        if g["voucher_id"] is None or g["entry_types"] == ["journal_entry"]
    )
    assert lone["lines"] == []
    assert lone["doc_status"] is None


def test_lines_do_not_change_the_vouchers_amount(client, voucher_seed):
    r = client.get(
        "/api/v1/erp-entries/vouchers?currency_mode=original", headers=auth("tokA")
    )

    group = next(g for g in r.json()["items"] if g["voucher_id"] == "4821")
    assert group["amount"] == "100.00"
    assert group["entry_count"] == 1, "payments stay excluded from listings"


def test_lines_do_not_change_which_vouchers_are_returned(client, voucher_seed, engine):
    with Session(engine) as s:
        for line in s.exec(select(InvoiceLine)).all():
            s.delete(line)
        s.commit()

    r = client.get(
        "/api/v1/erp-entries/vouchers?currency_mode=original", headers=auth("tokA")
    )

    voucher_ids = [g["voucher_id"] for g in r.json()["items"]]
    assert "4821" in voucher_ids
    group = next(g for g in r.json()["items"] if g["voucher_id"] == "4821")
    assert group["lines"] == []
    assert group["amount"] == "100.00"


def test_lines_are_tenant_scoped(client, voucher_seed):
    r = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokB"))
    assert r.status_code == 200

    descriptions = {l["description"] for g in r.json()["items"] for l in g["lines"]}
    assert "Cloud server" not in descriptions


def test_the_voucher_detail_carries_the_same_lines(client, voucher_seed):
    r = client.get("/api/v1/erp-entries/vouchers/4821", headers=auth("tokA"))
    assert r.status_code == 200

    invoice = r.json()["invoice"]
    assert [l["description"] for l in invoice["lines"]] == ["Cloud server", "Support"]
    assert invoice["doc_status"] == "not_applicable"


@pytest.fixture
def filterable(engine, voucher_seed):
    """Give Org A a second invoice, differing in date, supplier and origin."""

    ids = dict(voucher_seed)
    with Session(engine) as s:
        vendor = Vendor(name="Contoso ApS", country_code="DK")
        s.add(vendor)
        s.commit()

        other = Invoice(
            company_id=ids["comp_a"], invoice_number="A2",
            invoice_date=date(2025, 9, 15), currency="DKK",
            total=Decimal("40.00"), status="uncategorized", vendor_id=vendor.id,
        )
        s.add(other)
        s.commit()
        line = InvoiceLine(
            company_id=ids["comp_a"], invoice_id=other.id, description="Standing in",
            amount=Decimal("40.00"), status="uncategorized",
            origin=LineOrigin.ENTRY_FALLBACK,
        )
        s.add(line)
        s.commit()
        ids.update({"inv_a2": other.id, "line_a3": line.id, "vendor": vendor.id})
    return ids


def _descriptions(response) -> set[str]:
    return {item["description"] for item in response.json()["items"]}


def test_filter_by_period_bounds_the_invoice_date(client, filterable):
    r = client.get(
        "/api/v1/invoice-lines?from=2025-09-01&to=2025-09-30", headers=auth("tokA")
    )
    assert r.status_code == 200
    assert _descriptions(r) == {"Standing in"}


def test_filter_by_supplier_resolves_through_the_invoice(client, filterable):
    r = client.get(
        f"/api/v1/invoice-lines?vendor_id={filterable['vendor']}", headers=auth("tokA")
    )
    assert _descriptions(r) == {"Standing in"}


def test_filter_by_voucher_resolves_through_the_postings(client, filterable):
    r = client.get("/api/v1/invoice-lines?voucher_id=4821", headers=auth("tokA"))
    assert _descriptions(r) == {"Cloud server", "Support"}


def test_a_voucher_filter_does_not_duplicate_a_line(client, filterable, engine):
    with Session(engine) as s:
        s.add(ErpEntry(
            company_id=filterable["comp_a"], erp_account_id=filterable["account_a"],
            source_invoice_id=filterable["inv_a"], voucher_id="4821",
            entry_type="purchase_invoice", accounting_date=date(2025, 7, 1),
            debit_amount=Decimal("25.00"), currency="DKK",
        ))
        s.commit()

    r = client.get("/api/v1/invoice-lines?voucher_id=4821", headers=auth("tokA"))

    assert r.json()["total"] == 2
    assert len(r.json()["items"]) == 2


def test_filter_by_origin_finds_the_standins(client, filterable):
    r = client.get("/api/v1/invoice-lines?origin=entry_fallback", headers=auth("tokA"))
    assert _descriptions(r) == {"Standing in"}


def test_filters_compose(client, filterable):
    r = client.get(
        f"/api/v1/invoice-lines?vendor_id={filterable['vendor']}&from=2025-01-01"
        "&status=ai_categorized",
        headers=auth("tokA"),
    )
    assert r.json()["items"] == [], "all three must apply, not the last one alone"


def test_a_line_payload_states_its_origin(client, filterable):
    r = client.get("/api/v1/invoice-lines", headers=auth("tokA"))

    origins = {item["description"]: item["origin"] for item in r.json()["items"]}
    assert origins["Cloud server"] == "erp"
    assert origins["Standing in"] == "entry_fallback"


@pytest.fixture
def failed_invoice(engine, voucher_seed):
    with Session(engine) as s:
        invoice = s.get(Invoice, voucher_seed["inv_a"])
        invoice.doc_status = DocStatus.FAILED
        invoice.doc_error = "the document yielded no lines"
        invoice.doc_attempts = 3
        s.add(invoice)
        s.commit()
    return voucher_seed


def test_a_failed_invoice_is_queued_again(client, failed_invoice, engine):
    r = client.post(
        f"/api/v1/invoices/{failed_invoice['inv_a']}/reprocess", headers=auth("tokA")
    )
    assert r.status_code == 200
    assert r.json()["doc_status"] == "pending"
    assert r.json()["doc_error"] is None

    with Session(engine) as s:
        invoice = s.get(Invoice, failed_invoice["inv_a"])
    assert invoice.doc_attempts == 0, (
        "the ceiling is what stopped the stage retrying; a human asking is new "
        "information, so the count resets"
    )


def test_a_processed_invoice_may_still_be_redone(client, voucher_seed, engine):
    with Session(engine) as s:
        invoice = s.get(Invoice, voucher_seed["inv_a"])
        invoice.doc_status = DocStatus.PROCESSED
        s.add(invoice)
        s.commit()

    r = client.post(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/reprocess", headers=auth("tokA")
    )

    assert r.status_code == 200
    assert r.json()["doc_status"] == "pending"


def test_a_human_can_still_ask_to_re_read_an_invoice_they_verified(
    client, voucher_seed, engine
):
    with Session(engine) as s:
        invoice = s.get(Invoice, voucher_seed["inv_a"])
        invoice.doc_status = DocStatus.PROCESSED
        s.add(invoice)
        line = s.exec(
            select(InvoiceLine).where(InvoiceLine.invoice_id == voucher_seed["inv_a"])
        ).first()
        line.status = "verified"
        s.add(line)
        s.commit()

    r = client.post(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/reprocess", headers=auth("tokA")
    )

    assert r.status_code == 200
    assert r.json()["doc_status"] == "pending"


def test_reprocessing_an_invoice_with_no_document_is_refused(client, seed, engine):
    r = client.post(f"/api/v1/invoices/{seed['inv_a']}/reprocess", headers=auth("tokA"))

    assert r.status_code == 409
    with Session(engine) as s:
        assert s.get(Invoice, seed["inv_a"]).doc_status == "not_applicable"


def test_reprocessing_cannot_race_a_run_in_flight(client, voucher_seed, engine):
    with Session(engine) as s:
        invoice = s.get(Invoice, voucher_seed["inv_a"])
        invoice.doc_status = DocStatus.PROCESSING
        s.add(invoice)
        s.commit()

    r = client.post(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/reprocess", headers=auth("tokA")
    )

    assert r.status_code == 409


def test_a_read_only_member_cannot_retrigger(client, failed_invoice):
    r = client.post(
        f"/api/v1/invoices/{failed_invoice['inv_a']}/reprocess", headers=auth("tok_viewerA")
    )
    assert r.status_code == 403


def test_a_moderator_can_retrigger(client, failed_invoice):
    r = client.post(
        f"/api/v1/invoices/{failed_invoice['inv_a']}/reprocess",
        headers=auth("tok_moderatorA"),
    )
    assert r.status_code == 200


def test_another_tenants_invoice_is_not_found(client, failed_invoice):
    r = client.post(
        f"/api/v1/invoices/{failed_invoice['inv_b']}/reprocess", headers=auth("tokA")
    )
    assert r.status_code == 404


def test_the_retrigger_is_audited(client, failed_invoice, engine):
    client.post(
        f"/api/v1/invoices/{failed_invoice['inv_a']}/reprocess", headers=auth("tokA")
    )

    with Session(engine) as s:
        rows = s.exec(
            select(AuditLog).where(
                AuditLog.entity_id == failed_invoice["inv_a"],
                AuditLog.action == "reprocess_document",
            )
        ).all()
    assert len(rows) == 1
    with Session(engine) as s:
        actor = s.exec(select(User).where(User.clerk_user_id == "userA")).one()
    assert rows[0].actor == actor.id, "the acting user, not `system`"
    fields = {c["field"] for c in rows[0].changes}
    assert fields == {"doc_status", "doc_error"}
