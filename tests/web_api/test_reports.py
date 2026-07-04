"""Aggregate reporting endpoints: scoping, currency grouping, filters."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session

from web_api.db.models import ErpAccount, ErpEntry, ErpIntegration, Invoice, Vendor

from .conftest import auth


@pytest.fixture
def seed_reporting(engine, seed):
    """Entries (multi-currency) + a vendor + invoice vendor links on top of `seed`.

    Org A (comp_a): three DKK entries on account 6010 (two purchase_invoice
    debits 80+20, one payment credit 100) plus one EUR journal debit 50; its
    invoice `inv_a` is linked to vendor "Acme Supplies". Org B (comp_b): one DKK
    purchase_invoice debit 50.
    """
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

        def ent(company_id, account_id, **kw):
            s.add(ErpEntry(company_id=company_id, erp_account_id=account_id, **kw))

        ent(seed["comp_a"], acct_a.id, entry_type="purchase_invoice", currency="DKK",
            debit_amount=Decimal("80.00"), accounting_date=date(2025, 7, 15))
        ent(seed["comp_a"], acct_a.id, entry_type="purchase_invoice", currency="DKK",
            debit_amount=Decimal("20.00"), accounting_date=date(2025, 7, 15))
        ent(seed["comp_a"], acct_a.id, entry_type="payment", currency="DKK",
            credit_amount=Decimal("100.00"), accounting_date=date(2025, 7, 20))
        ent(seed["comp_a"], acct_a.id, entry_type="journal_entry", currency="EUR",
            debit_amount=Decimal("50.00"), accounting_date=date(2025, 8, 1))
        ent(seed["comp_b"], acct_b.id, entry_type="purchase_invoice", currency="DKK",
            debit_amount=Decimal("50.00"), accounting_date=date(2025, 8, 5))

        vendor = Vendor(name="Acme Supplies", country_code="DK")
        s.add(vendor)
        s.commit()
        inv_a = s.get(Invoice, seed["inv_a"])
        inv_a.vendor_id = vendor.id
        s.add(inv_a)
        s.commit()
        return {"vendor": vendor.id}


def _index(rows, *keys):
    return {tuple(r[k] for k in keys): r for r in rows}


# -- entries-summary ---------------------------------------------------------


def test_entries_summary_by_type_and_currency(client, seed_reporting):
    rows = client.get("/api/v1/reports/entries-summary", headers=auth("tokA")).json()["rows"]
    by = _index(rows, "entry_type", "currency")
    pi = by[("purchase_invoice", "DKK")]
    assert float(pi["debit_total"]) == 100.0 and float(pi["credit_total"]) == 0.0
    assert float(pi["net"]) == 100.0 and pi["count"] == 2
    pay = by[("payment", "DKK")]
    assert float(pay["net"]) == -100.0 and pay["count"] == 1
    # EUR journal entry is a separate row — currencies are never combined.
    assert ("journal_entry", "EUR") in by
    assert float(by[("journal_entry", "EUR")]["debit_total"]) == 50.0


def test_entries_summary_is_org_scoped(client, seed, seed_reporting):
    rows = client.get("/api/v1/reports/entries-summary", headers=auth("tokB")).json()["rows"]
    by = _index(rows, "entry_type", "currency")
    assert set(by) == {("purchase_invoice", "DKK")}
    assert float(by[("purchase_invoice", "DKK")]["debit_total"]) == 50.0


def test_entries_summary_foreign_company_is_404(client, seed, seed_reporting):
    r = client.get("/api/v1/reports/entries-summary", headers=auth("tokA"),
                   params={"company_id": seed["comp_b"]})
    assert r.status_code == 404


def test_entries_summary_empty_scope(client, seed_reporting):
    r = client.get("/api/v1/reports/entries-summary", headers=auth("tok_empty"))
    assert r.status_code == 200 and r.json() == {"rows": []}


def test_entries_summary_type_and_date_filters(client, seed_reporting):
    only_pay = client.get("/api/v1/reports/entries-summary", headers=auth("tokA"),
                          params={"entry_type": "payment"}).json()["rows"]
    assert {r["entry_type"] for r in only_pay} == {"payment"}

    # from excludes the 07-15 purchase invoices; keeps payment (07-20) + EUR (08-01).
    ranged = client.get("/api/v1/reports/entries-summary", headers=auth("tokA"),
                        params={"from": "2025-07-16"}).json()["rows"]
    assert {(r["entry_type"], r["currency"]) for r in ranged} == {
        ("payment", "DKK"), ("journal_entry", "EUR")}


# -- entries-by-account ------------------------------------------------------


def test_entries_by_account(client, seed_reporting):
    rows = client.get("/api/v1/reports/entries-by-account", headers=auth("tokA")).json()["rows"]
    by = _index(rows, "erp_account_code", "currency")
    dkk = by[("6010", "DKK")]
    assert float(dkk["debit_total"]) == 100.0 and float(dkk["credit_total"]) == 100.0
    assert float(dkk["net"]) == 0.0 and dkk["count"] == 3
    assert dkk["erp_account_name"] == "Cloud Hosting"
    assert float(by[("6010", "EUR")]["debit_total"]) == 50.0


# -- spend-by-category -------------------------------------------------------


def test_spend_by_category_counts_only_categorized_lines(client, seed_reporting):
    rows = client.get("/api/v1/reports/spend-by-category", headers=auth("tokA")).json()["rows"]
    # Only the ai_categorized line (Technology, 20.00 DKK) counts; the
    # uncategorized 80.00 line is excluded.
    assert len(rows) == 1
    row = rows[0]
    assert row["level_2"] == "Technology" and row["currency"] == "DKK"
    assert float(row["amount_total"]) == 20.0 and row["count"] == 1
    assert row["level_3"] is None  # default level_2 granularity


def test_spend_by_category_level_3_granularity(client, seed_reporting):
    rows = client.get("/api/v1/reports/spend-by-category", headers=auth("tokA"),
                      params={"level": "level_3"}).json()["rows"]
    assert len(rows) == 1 and "level_3" in rows[0]


# -- spend-by-vendor ---------------------------------------------------------


def test_spend_by_vendor(client, seed_reporting):
    rows = client.get("/api/v1/reports/spend-by-vendor", headers=auth("tokA")).json()["rows"]
    by = _index(rows, "vendor_name", "currency")
    acme = by[("Acme Supplies", "DKK")]
    assert float(acme["amount_total"]) == 100.0 and acme["count"] == 1
    assert acme["vendor_id"] == seed_reporting["vendor"]
