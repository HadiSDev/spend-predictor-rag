"""ERP entry read endpoints: filters, pagination, tenant isolation."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session

from web_api.db.models import ErpAccount, ErpEntry, ErpIntegration
from .conftest import auth


@pytest.fixture
def seed_entries(engine, seed):
    """Add ERP integrations, accounts, and entries for Org A (3) and Org B (1)."""
    ids: dict[str, str] = {}
    with Session(engine) as s:
        intg_a = ErpIntegration(company_id=seed["comp_a"], erp_type="mock")
        intg_b = ErpIntegration(company_id=seed["comp_b"], erp_type="mock")
        s.add(intg_a)
        s.add(intg_b)
        s.commit()
        acct_a = ErpAccount(erp_integration_id=intg_a.id, erp_account_code="6010",
                            erp_account_name="Cloud Hosting")
        acct_b = ErpAccount(erp_integration_id=intg_b.id, erp_account_code="6610",
                            erp_account_name="Legal Fees")
        s.add(acct_a)
        s.add(acct_b)
        s.commit()

        def ent(company_id, integration_id, account_id, **kw):
            row = ErpEntry(company_id=company_id, erp_integration_id=integration_id,
                           erp_account_id=account_id, **kw)
            s.add(row)
            return row

        a1 = ent(seed["comp_a"], intg_a.id, acct_a.id, voucher_id="V1",
                 entry_type="purchase_invoice", source_invoice_id=seed["inv_a"],
                 entry_date=date(2025, 7, 15), debit_amount=Decimal("80.00"),
                 status="pending")
        a2 = ent(seed["comp_a"], intg_a.id, acct_a.id, voucher_id="V1",
                 entry_type="purchase_invoice", source_invoice_id=seed["inv_a"],
                 entry_date=date(2025, 7, 15), debit_amount=Decimal("20.00"),
                 status="pending")
        a3 = ent(seed["comp_a"], intg_a.id, acct_a.id, voucher_id="PAY1",
                 entry_type="payment", entry_date=date(2025, 7, 20),
                 credit_amount=Decimal("100.00"), status="posted")
        b1 = ent(seed["comp_b"], intg_b.id, acct_b.id, voucher_id="VB",
                 entry_type="purchase_invoice", source_invoice_id=seed["inv_b"],
                 entry_date=date(2025, 8, 5), debit_amount=Decimal("50.00"), status="pending")
        s.commit()
        ids = {"a1": a1.id, "a2": a2.id, "a3": a3.id, "b1": b1.id}
    return ids


def test_list_scoped_with_total(client, seed_entries):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()
    assert body["total"] == 3
    assert {e["id"] for e in body["items"]} == {seed_entries["a1"], seed_entries["a2"], seed_entries["a3"]}


def test_list_does_not_leak_across_tenants(client, seed_entries):
    body = client.get("/api/v1/erp-entries", headers=auth("tokB")).json()
    ids = {e["id"] for e in body["items"]}
    assert ids == {seed_entries["b1"]}
    assert seed_entries["a1"] not in ids


def test_filter_by_source_invoice(client, seed, seed_entries):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                      params={"source_invoice_id": seed["inv_a"]}).json()
    assert {e["id"] for e in body["items"]} == {seed_entries["a1"], seed_entries["a2"]}


def test_filter_by_voucher_and_type(client, seed_entries):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                      params={"voucher_id": "V1", "entry_type": "purchase_invoice"}).json()
    assert body["total"] == 2
    payments = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                          params={"entry_type": "payment"}).json()
    assert {e["id"] for e in payments["items"]} == {seed_entries["a3"]}


def test_filter_by_status(client, seed_entries):
    pending = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                         params={"status": "pending"}).json()
    assert pending["total"] == 2
    posted = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                        params={"status": "posted"}).json()
    assert posted["total"] == 1


def test_pagination(client, seed_entries):
    r = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                   params={"page_size": 1, "page": 1}).json()
    assert r["page_size"] == 1
    assert len(r["items"]) == 1
    assert r["total"] == 3


def test_empty_scope_returns_empty_page(client, seed_entries):
    body = client.get("/api/v1/erp-entries", headers=auth("tok_empty")).json()
    assert body == {"items": [], "page": 1, "page_size": 50, "total": 0}


def test_detail_in_scope(client, seed_entries):
    r = client.get(f"/api/v1/erp-entries/{seed_entries['a1']}", headers=auth("tokA"))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == seed_entries["a1"]
    assert body["voucher_id"] == "V1"
    assert body["entry_type"] == "purchase_invoice"
    # Ground-truth and raw payload are not exposed.
    assert "gt_account_code" not in body
    assert "gt_level_1" not in body
    assert "raw_json" not in body


def test_detail_cross_tenant_is_404(client, seed_entries):
    r = client.get(f"/api/v1/erp-entries/{seed_entries['a1']}", headers=auth("tokB"))
    assert r.status_code == 404


def test_detail_unknown_is_404(client, seed_entries):
    r = client.get("/api/v1/erp-entries/does-not-exist", headers=auth("tokA"))
    assert r.status_code == 404
