"""One-request voucher detail endpoint: postings + invoice + document.

Uses `voucher_seed` (tests/web_api/conftest.py), which extends `seed` with a
connected ERP integration, one account, a `File`-linked Org A invoice, and
three postings on voucher "4821" (a purchase-invoice entry, a payment entry,
and — separately — a lone journal entry with no voucher at all).
"""
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
