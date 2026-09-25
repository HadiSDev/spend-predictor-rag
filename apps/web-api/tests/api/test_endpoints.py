"""Endpoint tests: org scoping, filters, pagination, cross-tenant isolation."""
from __future__ import annotations

from web_api_testkit import auth


def test_companies_are_org_scoped(client):
    a = client.get("/api/v1/companies", headers=auth("tokA")).json()
    b = client.get("/api/v1/companies", headers=auth("tokB")).json()
    assert [c["name"] for c in a] == ["Acme A"]
    assert [c["name"] for c in b] == ["Beta B"]


def test_invoices_scoped_and_status_filter(client):
    r = client.get("/api/v1/invoices", headers=auth("tokA"), params={"status": "uncategorized"})
    body = r.json()
    assert r.status_code == 200
    assert body["total"] == 1
    assert body["items"][0]["invoice_number"] == "A1"
    assert all(i["status"] == "uncategorized" for i in body["items"])


def test_invoices_do_not_leak_across_tenants(client, seed):
    body = client.get("/api/v1/invoices", headers=auth("tokB")).json()
    ids = {i["id"] for i in body["items"]}
    assert seed["inv_a"] not in ids
    assert ids == {seed["inv_b"]}


def test_invoices_pagination(client):
    r = client.get("/api/v1/invoices", headers=auth("tokA"), params={"page_size": 1, "page": 1})
    body = r.json()
    assert body["page_size"] == 1
    assert len(body["items"]) <= 1
    assert body["total"] == 1


def test_invoice_detail_includes_lines(client, seed):
    r = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA"))
    body = r.json()
    assert r.status_code == 200
    assert body["id"] == seed["inv_a"]
    assert len(body["lines"]) == 2
    descriptions = {ln["description"] for ln in body["lines"]}
    assert descriptions == {"Cloud server", "Support"}


def test_invoice_detail_cross_tenant_is_404(client, seed):
    r = client.get(f"/api/v1/invoices/{seed['inv_b']}", headers=auth("tokA"))
    assert r.status_code == 404


def test_foreign_company_id_filter_is_404(client, seed):
    r = client.get("/api/v1/invoices", headers=auth("tokA"), params={"company_id": seed["comp_b"]})
    assert r.status_code == 404


def test_own_company_id_filter_works(client, seed):
    r = client.get("/api/v1/invoices", headers=auth("tokA"), params={"company_id": seed["comp_a"]})
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_invoice_lines_uncategorized_only(client):
    r = client.get("/api/v1/invoice-lines", headers=auth("tokA"), params={"status": "uncategorized"})
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["description"] == "Cloud server"
    assert body["items"][0]["status"] == "uncategorized"


def test_invoice_lines_all_statuses(client):
    body = client.get("/api/v1/invoice-lines", headers=auth("tokA")).json()
    assert body["total"] == 2


def test_invoice_lines_scoped(client, seed):
    body = client.get("/api/v1/invoice-lines", headers=auth("tokB")).json()
    assert body["total"] == 1
    assert body["items"][0]["company_id"] == seed["comp_b"]


def test_empty_tenant_returns_empty_page(client):
    companies = client.get("/api/v1/companies", headers=auth("tok_empty"))
    assert companies.status_code == 200
    assert companies.json() == []

    invoices = client.get("/api/v1/invoice-lines", headers=auth("tok_empty"))
    assert invoices.status_code == 200
    assert invoices.json() == {"items": [], "page": 1, "page_size": 50, "total": 0}
