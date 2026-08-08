"""One-request voucher detail endpoint: postings + invoice + document.

Uses `voucher_seed` (tests/web_api/conftest.py), which extends `seed` with a
connected ERP integration, one account, a `File`-linked Org A invoice, and
three postings on voucher "4821" (a purchase-invoice entry, a payment entry,
and — separately — a lone journal entry with no voucher at all).
"""
from datetime import datetime, timezone

from sqlmodel import Session

from web_api.db.models import AuditLog

from .conftest import auth


def test_voucher_detail_returns_postings_invoice_and_document(client, voucher_seed):
    res = client.get("/api/v1/erp-entries/vouchers/4821", headers=auth("tokA"))

    assert res.status_code == 200
    body = res.json()
    assert body["voucher_id"] == "4821"
    assert body["company_id"] == voucher_seed["comp_a"]
    assert body["entry_count"] == 2
    assert body["invoice"]["id"] == voucher_seed["inv_a"]
    assert len(body["invoice"]["lines"]) == 2
    assert body["document"]["filename"] == "invoice.pdf"
    assert body["document"]["file_id"] == voucher_seed["file_a"]


def test_voucher_detail_includes_payment_postings(client, voucher_seed):
    """A voucher the user navigated to is a lookup, not a listing — hiding a
    posting would make the voucher's own totals unexplainable."""
    body = client.get("/api/v1/erp-entries/vouchers/4821", headers=auth("tokA")).json()

    assert {e["entry_type"] for e in body["entries"]} == {"purchase_invoice", "payment"}


def test_by_entry_resolves_a_posting_with_no_voucher(client, voucher_seed):
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{voucher_seed['entry_unvouchered']}",
        headers=auth("tokA"),
    )

    assert res.status_code == 200
    body = res.json()
    assert body["voucher_id"] is None
    assert len(body["entries"]) == 1
    assert body["invoice"] is None
    assert body["document"] is None


def test_by_entry_resolves_a_vouchered_posting_to_its_full_voucher(client, voucher_seed):
    """Naming any one posting on a voucher returns the whole voucher, not just
    that single entry — the payment posting is a real member of "4821" too."""
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{voucher_seed['entry_payment']}",
        headers=auth("tokA"),
    )

    assert res.status_code == 200
    body = res.json()
    assert body["voucher_id"] == "4821"
    assert body["entry_count"] == 2


def test_voucher_detail_is_tenant_scoped(client, voucher_seed):
    res = client.get("/api/v1/erp-entries/vouchers/4821", headers=auth("tokB"))
    assert res.status_code == 404


def test_voucher_detail_unknown_voucher_is_404(client, voucher_seed):
    res = client.get("/api/v1/erp-entries/vouchers/does-not-exist", headers=auth("tokA"))
    assert res.status_code == 404


def test_by_entry_unknown_entry_is_404(client, voucher_seed):
    res = client.get("/api/v1/erp-entries/vouchers/by-entry/does-not-exist", headers=auth("tokA"))
    assert res.status_code == 404


def test_by_entry_is_tenant_scoped(client, voucher_seed):
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{voucher_seed['entry_unvouchered']}",
        headers=auth("tokB"),
    )
    assert res.status_code == 404


# -- Voucher-wide audit feed --------------------------------------------------


def test_voucher_audit_merges_invoice_and_line_rows_newest_first(client, voucher_seed):
    """One chronological story for the voucher: a per-line history cannot answer
    'what happened to this voucher' without N requests."""
    client.post(f"/api/v1/invoice-lines/{voucher_seed['line_a1']}/verify",
                json={"level_2": "Technology"}, headers=auth("tokA"))
    client.post(f"/api/v1/invoice-lines/{voucher_seed['line_a2']}/verify",
                json={}, headers=auth("tokA"))

    res = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}/audit",
                     headers=auth("tokA"))

    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    assert [r["created_at"] for r in rows] == sorted(
        (r["created_at"] for r in rows), reverse=True
    )
    assert rows[0]["action"] == "verify"
    assert rows[1]["action"] == "edit"
    # Each row names what it happened to, so the feed needs no extra lookup.
    assert all(r["entity_label"] for r in rows)


def test_voucher_audit_by_entry_matches_direct_lookup(client, voucher_seed):
    """Naming any posting on the voucher returns the same audit feed as naming
    the voucher itself — the same inheritance the detail endpoint already has."""
    client.post(f"/api/v1/invoice-lines/{voucher_seed['line_a1']}/verify",
                json={"level_2": "Technology"}, headers=auth("tokA"))

    direct = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}/audit",
                        headers=auth("tokA")).json()
    by_entry = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{voucher_seed['entry_invoice']}/audit",
        headers=auth("tokA"),
    ).json()

    assert direct == by_entry
    assert len(direct) == 1


def test_voucher_audit_with_no_invoice_is_empty(client, voucher_seed):
    """A voucher (or lone posting) with no linked invoice has nothing to audit."""
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{voucher_seed['entry_unvouchered']}/audit",
        headers=auth("tokA"),
    )
    assert res.status_code == 200
    assert res.json() == []


def test_voucher_audit_is_tenant_scoped(client, voucher_seed):
    """A foreign voucher's audit trail is indistinguishable from a missing one."""
    res = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}/audit",
                     headers=auth("tokB"))
    assert res.status_code == 404


def test_voucher_audit_by_entry_is_tenant_scoped(client, voucher_seed):
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{voucher_seed['entry_invoice']}/audit",
        headers=auth("tokB"),
    )
    assert res.status_code == 404


def test_voucher_audit_unknown_voucher_is_404(client, voucher_seed):
    res = client.get("/api/v1/erp-entries/vouchers/does-not-exist/audit", headers=auth("tokA"))
    assert res.status_code == 404


def test_voucher_audit_orders_by_seq_not_created_at(client, engine, voucher_seed):
    """Two rows written in the same PostgreSQL transaction share `created_at`
    exactly — it is constant for the whole transaction there, not merely
    coarse-grained — so `created_at` alone carries no ordering information for
    them. `seq` (a true, monotonic insertion-order column) is what the feed
    must order by instead; this fabricates that tie directly and proves the
    feed's order is real and stable, not a coincidence of `created_at`."""
    tied = datetime(2025, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    with Session(engine) as s:
        row1 = AuditLog(entity_type="invoice_line", entity_id=voucher_seed["line_a1"],
                        action="ai_categorize", actor="system", changes=[], created_at=tied)
        s.add(row1)
        s.commit()
        row2 = AuditLog(entity_type="invoice_line", entity_id=voucher_seed["line_a2"],
                        action="ai_categorize", actor="system", changes=[], created_at=tied)
        s.add(row2)
        s.commit()
        # The tie is real, and seq still tells them apart in write order.
        assert row1.created_at == row2.created_at
        assert row1.seq < row2.seq
        expected_order = [row2.id, row1.id]  # newest (highest seq) first

    first = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}/audit",
                       headers=auth("tokA")).json()
    second = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}/audit",
                        headers=auth("tokA")).json()

    assert [r["id"] for r in first] == expected_order
    assert [r["id"] for r in second] == expected_order
