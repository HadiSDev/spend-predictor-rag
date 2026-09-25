"""Tests for the mock ERP entries endpoint and the MockErpConnector mapping."""
from __future__ import annotations

from fastapi.testclient import TestClient

from mock_erp.data.entries import _ACCOUNTS_PAYABLE, _VAT_INPUT_ACCOUNT
from mock_erp.main import app

_H = {"x-app-secret-token": "mock-secret"}


def _page_all(client: TestClient, path: str) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        body = client.get(path, params={"page": page, "pageSize": 100}, headers=_H).json()
        out.extend(body["collection"])
        if len(out) >= body["pagination"]["total"]:
            break
        page += 1
    return out


def test_entries_endpoint_pagination():
    with TestClient(app) as c:
        body = c.get("/api/v1/entries", params={"page": 1, "pageSize": 50}, headers=_H).json()
        assert "collection" in body and "pagination" in body
        assert 0 < len(body["collection"]) <= 50
        assert body["pagination"]["total"] > len(body["collection"])
        entry = body["collection"][0]
        assert "voucherId" in entry and "entryType" in entry
        assert entry["account"]["accountNumber"]


def test_entries_reconcile_with_invoice():
    with TestClient(app) as c:
        invoices = _page_all(c, "/api/v1/purchase-invoices")
        entries = _page_all(c, "/api/v1/entries")
        inv = invoices[0]
        v = inv["voucherId"]
        assert inv["file"]["fileName"]
        v_entries = [e for e in entries if e["voucherId"] == v]
        debit = round(sum(e["debit"] for e in v_entries), 2)
        credit = round(sum(e["credit"] for e in v_entries), 2)
        assert debit == inv["grossAmount"]
        assert debit == credit

        pay = {e["voucherId"] for e in entries if e["entryType"] == "payment"}
        inv_vouchers = {i["voucherId"] for i in invoices}
        assert pay and pay.isdisjoint(inv_vouchers)


def test_expense_postings_carry_their_invoice_line_text():
    with TestClient(app) as c:
        invoices = _page_all(c, "/api/v1/purchase-invoices")
        entries = _page_all(c, "/api/v1/entries")
        inv = next(i for i in invoices if len(i["lines"]) > 1)
        postings = [e for e in entries if e["voucherId"] == inv["voucherId"]]
        plumbing = {_ACCOUNTS_PAYABLE, _VAT_INPUT_ACCOUNT}
        expense = [e for e in postings
                   if e["account"]["accountNumber"] not in plumbing]

        assert [(e["description"], e["debit"]) for e in expense] == [
            (ln["description"], ln["netAmount"]) for ln in inv["lines"]
        ]


def test_a_posting_names_the_line_it_came_from():
    with TestClient(app) as c:
        invoices = _page_all(c, "/api/v1/purchase-invoices")
        entries = _page_all(c, "/api/v1/entries")
        inv = next(i for i in invoices if len(i["lines"]) > 1)
        postings = [e for e in entries if e["voucherId"] == inv["voucherId"]]
        plumbing = {_ACCOUNTS_PAYABLE, _VAT_INPUT_ACCOUNT}

        expense = [e for e in postings if e["account"]["accountNumber"] not in plumbing]
        assert [e["lineNumber"] for e in expense] == [ln["lineNumber"] for ln in inv["lines"]]
        assert all(e["lineNumber"] is None
                   for e in postings if e["account"]["accountNumber"] in plumbing)


def test_connector_carries_the_source_line_id(mock_erp_connector):
    entries = mock_erp_connector.fetch_entries()
    linked = [e for e in entries if e.source_line_erp_id is not None]
    assert linked and all(e.source_line_erp_id.isdigit() for e in linked)
    assert any(e.source_line_erp_id is None for e in entries)


def test_entries_since_filter():
    with TestClient(app) as c:
        all_entries = _page_all(c, "/api/v1/entries")
        cutoff = sorted(e["date"] for e in all_entries)[len(all_entries) // 2]
        body = c.get("/api/v1/entries", params={"page": 1, "pageSize": 100, "since": cutoff},
                     headers=_H).json()
        assert all(e["date"] >= cutoff for e in body["collection"])


def test_connector_fetch_entries(mock_erp_connector):
    entries = mock_erp_connector.fetch_entries()
    assert entries
    e = entries[0]
    assert e.voucher_id
    assert e.erp_account_code
    assert e.entry_type in {"purchase_invoice", "payment", "journal_entry", "credit_note"}


def test_connector_fetch_invoice_scan(mock_erp_connector):
    entries = mock_erp_connector.fetch_entries()
    voucher = next(e.voucher_id for e in entries if e.entry_type == "purchase_invoice")
    scan = mock_erp_connector.fetch_invoice_scan(voucher)
    assert scan is not None
    assert scan.voucher_id == voucher
    assert scan.file_name and scan.file_ref
    assert scan.lines

    assert mock_erp_connector.fetch_invoice_scan("does-not-exist") is None


def test_connector_fetch_entries_account_filter(mock_erp_connector):
    only_6010 = mock_erp_connector.fetch_entries(account_codes={"6010"})
    assert only_6010
    assert all(e.erp_account_code == "6010" for e in only_6010)
    assert mock_erp_connector.fetch_entries(account_codes=set()) == []
    all_codes = {e.erp_account_code for e in mock_erp_connector.fetch_entries()}
    assert len(all_codes) > 1


def test_connector_accounts_expose_with_vat(mock_erp_connector):
    accounts = mock_erp_connector.fetch_accounts()
    vat_flags = {a.with_vat for a in accounts}
    assert vat_flags == {True, False}
    by_code = {a.erp_account_code: a for a in accounts}
    assert by_code["6010"].with_vat is True
    assert by_code["2100"].with_vat is False


def test_accounts_endpoint_includes_with_vat():
    with TestClient(app) as c:
        body = c.get("/api/v1/accounts", params={"page": 1, "pageSize": 100}, headers=_H).json()
        assert all("withVat" in a for a in body["collection"])


def test_entries_endpoint_account_filter():
    with TestClient(app) as c:
        body = c.get("/api/v1/entries", params={"page": 1, "pageSize": 100, "accounts": "6010,6020"},
                     headers=_H).json()
        nums = {e["account"]["accountNumber"] for e in body["collection"]}
        assert nums <= {6010, 6020}
        assert body["collection"]


def test_document_route_returns_a_pdf_for_a_voucher_with_an_invoice():
    with TestClient(app) as c:
        invoices = c.get("/api/v1/purchase-invoices", headers=_H).json()["collection"]
        voucher_id = invoices[0]["voucherId"]

        res = c.get(f"/api/v1/documents/{voucher_id}", headers=_H)

        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content.startswith(b"%PDF-")


def test_document_route_404s_for_a_voucher_with_no_invoice():
    with TestClient(app) as c:
        res = c.get("/api/v1/documents/99999999", headers=_H)
        assert res.status_code == 404
