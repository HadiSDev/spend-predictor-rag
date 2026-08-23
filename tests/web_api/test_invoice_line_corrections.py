"""Correcting, adding and deleting invoice lines.

The spend category has its own endpoint and its own tests (`test_verify.py`,
`test_verify_spend_tree.py`); what is under test here is everything else a human
may say about a line — what was bought, how much of it, and at what price — plus
the two operations that change an invoice's line *set*.
"""
from __future__ import annotations

from decimal import Decimal

from sqlmodel import Session, select

from web_api.db.models import AuditLog, ErpEntry, Invoice, InvoiceLine

from .conftest import auth


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


# -- Correcting a line ---------------------------------------------------------


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
    """The base figures were derived from the pre-correction amount. Once it
    moves they describe nothing real, and are cleared rather than recomputed at
    a substitute rate."""
    assert _line(engine, seed["line_a1"]).base_amount == Decimal("80.00")

    body = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                        json={"amount": "95.00"}, headers=auth("tokA")).json()

    assert body["amount"] == "95.00"
    assert body["base_amount"] is None
    assert body["base_currency"] is None
    assert body["fx_rate"] is None
    assert body["fx_rate_date"] is None

    # The cleared conversion rides in the same audit entry as the correction, so
    # the trail shows the whole effect rather than only what was asked for.
    changed = {c["field"] for c in _audit(engine, "invoice_line", seed["line_a1"])[0].changes}
    assert {"amount", "base_amount", "fx_rate"} <= changed


def test_correcting_only_a_description_leaves_the_conversion_intact(client, seed, engine):
    client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                 json={"description": "Renamed"}, headers=auth("tokA"))

    line = _line(engine, seed["line_a1"])
    assert line.base_amount == Decimal("80.00")
    assert line.fx_rate == Decimal("1")


def test_correcting_the_item_name_stores_it_and_audits_the_old_value(client, seed, engine):
    """The name is what was bought. Applied in place, so the audit row is the
    only record of what the source had stated."""
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
    """A reviewer splitting a stand-in may legitimately have nothing to name, so
    an explicit null is a correction rather than a rejected value."""
    client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                 json={"item_name": "Hetzner CX41"}, headers=auth("tokA"))

    body = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                        json={"item_name": None}, headers=auth("tokA")).json()

    assert body["item_name"] is None
    assert _line(engine, seed["line_a1"]).item_name is None


def test_the_name_and_the_description_are_corrected_independently(client, seed, engine):
    """One field was doing both jobs before this; correcting either must not
    disturb the other, or the split would be cosmetic."""
    client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                 json={"item_name": "Hetzner CX41"}, headers=auth("tokA"))

    body = client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                        json={"description": "Monthly, 8 vCPU"}, headers=auth("tokA")).json()

    assert body["item_name"] == "Hetzner CX41"
    assert body["description"] == "Monthly, 8 vCPU"


def test_correcting_only_the_item_name_leaves_the_conversion_intact(client, seed, engine):
    """A name is not an input to any conversion, so the base figures stand."""
    client.patch(f"/api/v1/invoice-lines/{seed['line_a1']}",
                 json={"item_name": "Hetzner CX41"}, headers=auth("tokA"))

    assert _line(engine, seed["line_a1"]).base_amount == Decimal("80.00")


def test_a_category_cannot_be_smuggled_alongside_an_item_name(client, seed, engine):
    """The whole payload is refused, not the offending key alone — a partially
    applied correction is the outcome `extra="forbid"` exists to prevent."""
    res = client.patch(f"/api/v1/invoice-lines/{seed['line_a2']}",
                       json={"item_name": "Support plan", "level_2": "Facilities"},
                       headers=auth("tokA"))

    assert res.status_code == 422
    line = _line(engine, seed["line_a2"])
    assert line.level_2 == "Technology"
    assert line.item_name is None


def test_a_category_cannot_be_smuggled_through_the_value_endpoint(client, seed, engine):
    """Silently ignoring it would read to the caller as a category edit that did
    nothing. A category is corrected through `verify`, which resolves it against
    the company's tree."""
    res = client.patch(f"/api/v1/invoice-lines/{seed['line_a2']}",
                       json={"level_2": "Facilities"}, headers=auth("tokA"))

    assert res.status_code == 422
    assert _line(engine, seed["line_a2"]).level_2 == "Technology"


def test_the_posted_account_code_is_not_correctable(client, seed):
    """It is the ledger's own statement of where the money was posted; a value
    contradicting it reconciles against nothing."""
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


# -- Adding a line -------------------------------------------------------------


def test_an_added_line_is_human_and_uncategorized(client, seed):
    res = client.post(f"/api/v1/invoices/{seed['inv_a']}/lines",
                      json={"description": "Freight", "amount": "40.00"},
                      headers=auth("tokA"))

    assert res.status_code == 201
    body = res.json()
    assert body["origin"] == "human"
    assert body["status"] == "uncategorized"
    assert body["description"] == "Freight"
    # After the seed's two lines (sequences 0 and 1), which is what appending
    # means — an invoice reads top to bottom.
    assert body["sequence"] == 2


def test_an_explicit_sequence_is_honoured(client, seed):
    body = client.post(f"/api/v1/invoices/{seed['inv_a']}/lines",
                       json={"description": "Inserted", "sequence": 1},
                       headers=auth("tokA")).json()
    assert body["sequence"] == 1


def test_adding_a_line_is_recorded_on_the_invoice(client, seed, engine):
    """The invoice's own history is where a reader looks to learn that its line
    set changed."""
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


# -- Deleting a line -----------------------------------------------------------


def test_deleting_a_line_keeps_its_values_in_the_audit_trail(client, seed, engine):
    """For a verified line this entry is the only surviving trace that a human's
    decision ever existed."""
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
    """The line's own history becomes unreachable through a row that no longer
    exists — nobody would think to look up an id they can no longer see."""
    client.delete(f"/api/v1/invoice-lines/{seed['line_a2']}", headers=auth("tokA"))

    rows = _audit(engine, "invoice", seed["inv_a"])
    assert [r.action for r in rows] == ["line_deleted"]
    assert rows[0].changes == [{"field": "line_id", "old": seed["line_a2"], "new": None}]


def test_postings_survive_their_lines_deletion(client, seed, engine, voucher_seed):
    """An `ErpEntry` is the ledger's own evidence and is never deleted with a
    line; the reference is nulled, as the document stage does on replacement."""
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
        # Only the verified line is left, so the invoice rolls up to verified.
        assert s.get(Invoice, seed["inv_a"]).status == "verified"


def test_deleting_requires_management(client, seed, engine):
    res = client.delete(f"/api/v1/invoice-lines/{seed['line_a1']}", headers=auth("tok_viewerA"))

    assert res.status_code == 403
    assert _line(engine, seed["line_a1"]) is not None


def test_deleting_a_foreign_line_is_404(client, seed, engine):
    res = client.delete(f"/api/v1/invoice-lines/{seed['line_b1']}", headers=auth("tokA"))

    assert res.status_code == 404
    assert _line(engine, seed["line_b1"]) is not None


# -- Splitting a stand-in, which is what the whole feature is for --------------


def test_splitting_a_stand_in_line(client, seed, engine):
    """Add the real lines, then delete the stand-in. The invoice holds a `human`
    line beside the original in between, which the one-origin rule permits
    precisely so this operation can be done a step at a time."""
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
    # 20 + 60 + 20 against a total of 100 — the split reconciles.
    assert detail["lines_reconciled"] is True
