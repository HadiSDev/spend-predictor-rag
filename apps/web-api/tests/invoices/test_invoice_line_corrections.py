"""Correcting, adding and deleting invoice lines."""
from __future__ import annotations

from decimal import Decimal

from sqlmodel import Session, select

from web_api.db.models import AuditLog, ErpEntry, Invoice, InvoiceLine

from web_api_testkit import auth


def _line(engine, line_id: str) -> InvoiceLine:
    with Session(engine) as s:
        return s.get(InvoiceLine, line_id)


def _audit(engine, entity_type: str, entity_id: str) -> list[AuditLog]:
    with Session(engine) as s:
        return s.exec(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at, AuditLog.id)
        ).all()


def test_correcting_a_description_stores_it_and_audits_the_diff(client, seed, engine):
    res = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                       json={"description": "Dell U2724DE monitor"}, headers=auth("tokA"))

    assert res.status_code == 200
    assert res.json()["description"] == "Dell U2724DE monitor"

    rows = _audit(engine, "invoice_line", seed["line_a1"])
    assert [r.action for r in rows] == ["edit"]
    assert {"field": "description", "old": "Cloud server",
            "new": "Dell U2724DE monitor"} in rows[0].changes


def test_a_correction_settles_the_field_against_the_next_sync(client, seed):
    body = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                        json={"quantity": "3", "unit": "pcs"}, headers=auth("tokA")).json()

    assert body["verified_fields"] == ["quantity", "unit"]


def test_correcting_the_amount_clears_the_line_conversion(client, seed, engine):
    assert _line(engine, seed["line_a1"]).base_amount == Decimal("80.00")

    body = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                        json={"amount": "95.00"}, headers=auth("tokA")).json()

    assert body["amount"] == "95.00"
    assert body["base_amount"] is None
    assert body["base_currency"] is None
    assert body["fx_rate"] is None
    assert body["fx_rate_date"] is None

    changed = {c["field"] for c in _audit(engine, "invoice_line", seed["line_a1"])[0].changes}
    assert {"amount", "base_amount", "fx_rate"} <= changed


def test_correcting_only_a_description_leaves_the_conversion_intact(client, seed, engine):
    client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                 json={"description": "Renamed"}, headers=auth("tokA"))

    line = _line(engine, seed["line_a1"])
    assert line.base_amount == Decimal("80.00")
    assert line.fx_rate == Decimal("1")


def test_correcting_the_item_name_stores_it_and_audits_the_old_value(client, seed, engine):
    res = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                       json={"item_name": "Hetzner CX41"}, headers=auth("tokA"))

    assert res.status_code == 200
    assert res.json()["item_name"] == "Hetzner CX41"

    rows = _audit(engine, "invoice_line", seed["line_a1"])
    assert [r.action for r in rows] == ["edit"]
    assert {"field": "item_name", "old": None, "new": "Hetzner CX41"} in rows[0].changes


def test_a_corrected_item_name_is_settled_against_the_next_sync(client, seed):
    body = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                        json={"item_name": "Hetzner CX41"}, headers=auth("tokA")).json()

    assert body["verified_fields"] == ["item_name"]


def test_the_item_name_can_be_cleared(client, seed, engine):
    client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                 json={"item_name": "Hetzner CX41"}, headers=auth("tokA"))

    body = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                        json={"item_name": None}, headers=auth("tokA")).json()

    assert body["item_name"] is None
    assert _line(engine, seed["line_a1"]).item_name is None


def test_the_name_and_the_description_are_corrected_independently(client, seed, engine):
    client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                 json={"item_name": "Hetzner CX41"}, headers=auth("tokA"))

    body = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                        json={"description": "Monthly, 8 vCPU"}, headers=auth("tokA")).json()

    assert body["item_name"] == "Hetzner CX41"
    assert body["description"] == "Monthly, 8 vCPU"


def test_correcting_only_the_item_name_leaves_the_conversion_intact(client, seed, engine):
    client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                 json={"item_name": "Hetzner CX41"}, headers=auth("tokA"))

    assert _line(engine, seed["line_a1"]).base_amount == Decimal("80.00")


def test_a_category_cannot_be_smuggled_alongside_an_item_name(client, seed, engine):
    res = client.patch(f"/api/v1/invoice-lines/{seed['line_a2']}",
                       json={"item_name": "Support plan", "level_2": "Facilities"},
                       headers=auth("tokA"))

    assert res.status_code == 422
    line = _line(engine, seed["line_a2"])
    assert line.level_2 == "Technology"
    assert line.item_name is None


def test_a_category_cannot_be_smuggled_through_the_value_endpoint(client, seed, engine):
    res = client.patch(f"/api/v1/invoice-lines/{seed['line_a2']}",
                       json={"level_2": "Facilities"}, headers=auth("tokA"))

    assert res.status_code == 422
    assert _line(engine, seed["line_a2"]).level_2 == "Technology"


def test_the_posted_account_code_is_not_correctable(client, seed):
    res = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                       json={"native_account_code": "9999"}, headers=auth("tokA"))
    assert res.status_code == 422


def test_correcting_requires_management(client, seed):
    res = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                       json={"description": "X"}, headers=auth("tok_viewerA"))
    assert res.status_code == 403


def test_correcting_a_foreign_line_is_404(client, seed, engine):
    res = client.patch(f"/api/v1/invoice-lines/{seed['line_b1']}",
                       json={"description": "X"}, headers=auth("tokA"))

    assert res.status_code == 404
    assert _line(engine, seed["line_b1"]).description == "Legal retainer"


def test_an_added_line_is_human_and_uncategorized(client, seed):
    res = client.post(f"/api/v1/invoices/{seed['inv_a']}/lines",
                      json={"description": "Freight", "amount": "40.00"},
                      headers=auth("tokA"))

    assert res.status_code == 201
    body = res.json()
    assert body["origin"] == "human"
    assert body["status"] == "uncategorized"
    assert body["description"] == "Freight"
    assert body["sequence"] == 2


def test_an_explicit_sequence_is_honoured(client, seed):
    body = client.post(f"/api/v1/invoices/{seed['inv_a']}/lines",
                       json={"description": "Inserted", "sequence": 1},
                       headers=auth("tokA")).json()
    assert body["sequence"] == 1


def test_adding_a_line_is_recorded_on_the_invoice(client, seed, engine):
    line_id = client.post(f"/api/v1/invoices/{seed['inv_a']}/lines",
                          json={"description": "Freight"}, headers=auth("tokA")).json()["id"]

    rows = _audit(engine, "invoice", seed["inv_a"])
    assert [r.action for r in rows] == ["line_added"]
    assert rows[0].changes == [{"field": "line_id", "old": None, "new": line_id}]


def test_adding_requires_management(client, seed):
    res = client.post(f"/api/v1/invoices/{seed['inv_a']}/lines",
                      json={"description": "X"}, headers=auth("tok_viewerA"))
    assert res.status_code == 403


def test_adding_to_a_foreign_invoice_is_404(client, seed):
    res = client.post(f"/api/v1/invoices/{seed['inv_b']}/lines",
                      json={"description": "X"}, headers=auth("tokA"))
    assert res.status_code == 404


def test_deleting_a_line_keeps_its_values_in_the_audit_trail(client, seed, engine):
    res = client.delete(f"/api/v1/invoice-lines/{seed['line_a2']}", headers=auth("tokA"))

    assert res.status_code == 204
    assert _line(engine, seed["line_a2"]) is None

    rows = _audit(engine, "invoice_line", seed["line_a2"])
    assert [r.action for r in rows] == ["line_deleted"]
    recorded = {c["field"]: c["old"] for c in rows[0].changes}
    assert recorded["description"] == "Support"
    assert recorded["amount"] == "20.00"
    assert recorded["level_2"] == "Technology"
    assert recorded["account_code"] == "6010"


def test_a_deletion_is_also_recorded_on_the_invoice(client, seed, engine):
    client.delete(f"/api/v1/invoice-lines/{seed['line_a2']}", headers=auth("tokA"))

    rows = _audit(engine, "invoice", seed["inv_a"])
    assert [r.action for r in rows] == ["line_deleted"]
    assert rows[0].changes == [{"field": "line_id", "old": seed["line_a2"], "new": None}]


def test_postings_survive_their_lines_deletion(client, seed, engine, voucher_seed):
    with Session(engine) as s:
        entries = s.exec(
            select(ErpEntry).where(ErpEntry.source_invoice_id == seed["inv_a"])
        ).all()
        assert entries, "the voucher_seed fixture must give us postings to check"
        for entry in entries:
            entry.source_invoice_line_id = seed["line_a1"]
            s.add(entry)
        s.commit()
        entry_ids = [e.id for e in entries]

    res = client.delete(f"/api/v1/invoice-lines/{seed['line_a1']}", headers=auth("tokA"))
    assert res.status_code == 204

    with Session(engine) as s:
        for entry_id in entry_ids:
            entry = s.get(ErpEntry, entry_id)
            assert entry is not None
            assert entry.source_invoice_line_id is None


def test_deleting_the_last_categorized_line_recomputes_the_rollup(client, seed, engine):
    client.post(f"/api/v1/invoice-lines/{seed['line_a2']}/verify", headers=auth("tokA"))
    client.delete(f"/api/v1/invoice-lines/{seed['line_a1']}", headers=auth("tokA"))

    with Session(engine) as s:
        assert s.get(Invoice, seed["inv_a"]).status == "verified"


def test_deleting_requires_management(client, seed, engine):
    res = client.delete(f"/api/v1/invoice-lines/{seed['line_a1']}", headers=auth("tok_viewerA"))

    assert res.status_code == 403
    assert _line(engine, seed["line_a1"]) is not None


def test_deleting_a_foreign_line_is_404(client, seed, engine):
    res = client.delete(f"/api/v1/invoice-lines/{seed['line_b1']}", headers=auth("tokA"))

    assert res.status_code == 404
    assert _line(engine, seed["line_b1"]) is not None


def test_splitting_a_stand_in_line(client, seed, engine):
    for description, amount in (("Monitor", "60.00"), ("Cables", "20.00")):
        res = client.post(f"/api/v1/invoices/{seed['inv_a']}/lines",
                          json={"description": description, "amount": amount},
                          headers=auth("tokA"))
        assert res.status_code == 201
    assert client.delete(
        f"/api/v1/invoice-lines/{seed['line_a1']}", headers=auth("tokA")
    ).status_code == 204

    detail = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA")).json()
    descriptions = [l["description"] for l in detail["lines"]]
    assert descriptions == ["Support", "Monitor", "Cables"]
    assert detail["lines_reconciled"] is True


def test_a_shipping_charge_is_corrected_and_deleted_like_any_other_line(
    client, seed, engine
):
    with Session(engine) as s:
        invoice_id = s.get(InvoiceLine, seed["line_a1"]).invoice_id

    created = client.post(
        f"/api/v1/invoices/{invoice_id}/lines",
        json={"description": "shipping cost incl. VAT", "amount": "15.90"},
        headers=auth("tokA"),
    )
    assert created.status_code == 201
    charge_id = created.json()["id"]

    corrected = client.patch(
        f"/api/v1/invoice-lines/{charge_id}",
        json={"description": "Freight", "amount": "15.90"},
        headers=auth("tokA"),
    )
    assert corrected.status_code == 200
    assert corrected.json()["description"] == "Freight"

    assert client.delete(
        f"/api/v1/invoice-lines/{charge_id}", headers=auth("tokA")
    ).status_code == 204
    assert _line(engine, charge_id) is None
