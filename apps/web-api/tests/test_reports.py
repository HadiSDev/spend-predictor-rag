"""Aggregate reporting endpoints: scoping, currency grouping, filters."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from web_api.db.models import (
    ErpAccount,
    ErpEntry,
    ErpIntegration,
    Invoice,
    InvoiceLine,
    Vendor,
)

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

        def ent(company_id, account_id, rate="1", **kw):
            """Add an entry, converted into DKK at `rate` unless told otherwise.

            `rate=None` leaves it unconverted — the outage/unsupported-currency
            case, which base-mode reporting must count rather than swallow.
            """
            if rate is not None:
                rate = Decimal(rate)
                kw["base_currency"] = "DKK"
                kw["fx_rate"] = rate
                kw["fx_rate_date"] = kw.get("accounting_date")
                for posted, base in (("debit_amount", "base_debit_amount"),
                                     ("credit_amount", "base_credit_amount")):
                    if kw.get(posted) is not None:
                        kw[base] = (kw[posted] * rate).quantize(Decimal("0.01"))
            s.add(ErpEntry(company_id=company_id, erp_account_id=account_id, **kw))

        ent(seed["comp_a"], acct_a.id, entry_type="purchase_invoice", currency="DKK",
            debit_amount=Decimal("80.00"), accounting_date=date(2025, 7, 15))
        ent(seed["comp_a"], acct_a.id, entry_type="purchase_invoice", currency="DKK",
            debit_amount=Decimal("20.00"), accounting_date=date(2025, 7, 15))
        ent(seed["comp_a"], acct_a.id, entry_type="payment", currency="DKK",
            credit_amount=Decimal("100.00"), accounting_date=date(2025, 7, 20))
        # Posted in EUR, converted to DKK at 7.46 — 50 EUR becomes 373.00 DKK.
        # This is the row that makes the two currency modes differ.
        ent(seed["comp_a"], acct_a.id, entry_type="journal_entry", currency="EUR",
            debit_amount=Decimal("50.00"), accounting_date=date(2025, 8, 1),
            rate="7.46")
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


# Sums as posted, rather than the default base-currency sums.
ORIGINAL = {"currency_mode": "original"}


# -- entries-summary ---------------------------------------------------------


def test_entries_summary_by_type_and_currency(client, seed_reporting):
    """Original mode: one row per posted currency, never combined."""
    rows = client.get("/api/v1/reports/entries-summary", headers=auth("tokA"),
                      params=ORIGINAL).json()["rows"]
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
                        params={"from": "2025-07-16", **ORIGINAL}).json()["rows"]
    assert {(r["entry_type"], r["currency"]) for r in ranged} == {
        ("payment", "DKK"), ("journal_entry", "EUR")}


# -- entries-by-account ------------------------------------------------------


def test_entries_by_account(client, seed_reporting):
    rows = client.get("/api/v1/reports/entries-by-account", headers=auth("tokA"),
                      params=ORIGINAL).json()["rows"]
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


# -- currency modes ----------------------------------------------------------
#
# Org A posts in DKK and EUR and reports in DKK. Base mode is the point of the
# feature: one figure, in the currency the customer reads.


def test_base_mode_is_the_default(client, seed_reporting):
    default = client.get("/api/v1/reports/entries-summary", headers=auth("tokA")).json()
    explicit = client.get("/api/v1/reports/entries-summary", headers=auth("tokA"),
                          params={"currency_mode": "base"}).json()
    assert default == explicit


def test_base_mode_reports_the_eur_posting_in_dkk(client, seed_reporting):
    rows = client.get("/api/v1/reports/entries-summary", headers=auth("tokA")).json()["rows"]
    by = _index(rows, "entry_type", "currency")

    # The EUR journal entry is no longer its own currency row: 50 EUR at 7.46.
    assert ("journal_entry", "EUR") not in by
    journal = by[("journal_entry", "DKK")]
    assert float(journal["debit_total"]) == 373.0


def test_base_mode_yields_one_currency_per_dimension(client, seed_reporting):
    rows = client.get("/api/v1/reports/entries-by-account", headers=auth("tokA")).json()["rows"]

    # One account, one row — where original mode splits it into DKK and EUR.
    assert [r["currency"] for r in rows] == ["DKK"]
    assert float(rows[0]["debit_total"]) == 100.0 + 373.0


def test_original_mode_is_unchanged_by_conversion(client, seed_reporting):
    rows = client.get("/api/v1/reports/entries-by-account", headers=auth("tokA"),
                      params=ORIGINAL).json()["rows"]
    by = _index(rows, "erp_account_code", "currency")

    # The posted figures, untouched: 50 EUR is still 50 EUR.
    assert float(by[("6010", "EUR")]["debit_total"]) == 50.0
    assert float(by[("6010", "DKK")]["debit_total"]) == 100.0
    assert all(r["unconverted_count"] == 0 for r in rows)


@pytest.mark.parametrize("mode", ["usd", "BASE", "", "converted"])
def test_an_unknown_currency_mode_is_rejected(client, seed_reporting, mode):
    r = client.get("/api/v1/reports/entries-summary", headers=auth("tokA"),
                   params={"currency_mode": mode})
    assert r.status_code == 422


# -- unconverted money is counted, never dropped ------------------------------


@pytest.fixture
def unconverted_entry(engine, seed, seed_reporting):
    """A GBP posting no rate was available for — stored, but not converted."""
    with Session(engine) as s:
        account = s.exec(select(ErpAccount)).first()
        s.add(ErpEntry(company_id=seed["comp_a"], erp_account_id=account.id,
                       entry_type="journal_entry", currency="GBP",
                       debit_amount=Decimal("1000.00"),
                       accounting_date=date(2025, 8, 2)))
        s.commit()


def test_unconverted_money_is_reported_as_its_own_row(client, unconverted_entry):
    rows = client.get("/api/v1/reports/entries-summary", headers=auth("tokA")).json()["rows"]
    by = _index(rows, "entry_type", "currency")

    unconverted = by[("journal_entry", None)]
    assert unconverted["unconverted_count"] == 1
    # Counted and visible, but not added to a DKK total it is not in.
    assert float(unconverted["debit_total"]) == 0.0
    assert float(by[("journal_entry", "DKK")]["debit_total"]) == 373.0


def test_the_unconverted_posting_is_not_folded_into_the_base_total(client, unconverted_entry):
    rows = client.get("/api/v1/reports/entries-by-account", headers=auth("tokA")).json()["rows"]
    converted = next(r for r in rows if r["currency"] == "DKK")

    # 1000 GBP must not appear as 1000 DKK.
    assert float(converted["debit_total"]) == 100.0 + 373.0
    assert converted["unconverted_count"] == 0


def test_original_mode_still_shows_the_unconverted_posting_in_full(client, unconverted_entry):
    rows = client.get("/api/v1/reports/entries-by-account", headers=auth("tokA"),
                      params=ORIGINAL).json()["rows"]
    by = _index(rows, "erp_account_code", "currency")

    assert float(by[("6010", "GBP")]["debit_total"]) == 1000.0


def test_a_wholly_unconverted_dimension_still_appears(client, engine, seed, seed_reporting):
    """A category nobody could convert is reported at zero, not omitted."""
    with Session(engine) as s:
        line = s.get(InvoiceLine, seed["line_a2"])
        line.base_currency = None
        line.base_amount = None
        line.fx_rate = None
        s.add(line)
        s.commit()

    rows = client.get("/api/v1/reports/spend-by-category", headers=auth("tokA")).json()["rows"]

    assert len(rows) == 1
    assert rows[0]["level_2"] == "Technology"
    assert rows[0]["currency"] is None
    assert float(rows[0]["amount_total"]) == 0.0
    assert rows[0]["unconverted_count"] == 1


def test_a_company_mid_recompute_is_not_silently_merged(client, engine, seed, seed_reporting):
    """Half-recomputed rows show as two currencies, not one wrong number."""
    with Session(engine) as s:
        entry = s.exec(select(ErpEntry).where(ErpEntry.entry_type == "payment")).one()
        entry.base_currency = "EUR"  # left over from a previous base currency
        s.add(entry)
        s.commit()

    rows = client.get("/api/v1/reports/entries-summary", headers=auth("tokA")).json()["rows"]
    payments = [r for r in rows if r["entry_type"] == "payment"]

    assert {r["currency"] for r in payments} == {"EUR"}
    # The DKK rows are still their own, so nothing was added across currencies.
    assert {r["currency"] for r in rows if r["entry_type"] == "purchase_invoice"} == {"DKK"}


# -- invoice-layer reports ----------------------------------------------------


def test_spend_by_vendor_reports_the_base_currency(client, seed_reporting):
    rows = client.get("/api/v1/reports/spend-by-vendor", headers=auth("tokA")).json()["rows"]
    assert [r["currency"] for r in rows] == ["DKK"]
    assert float(rows[0]["amount_total"]) == 100.0


def test_spend_by_category_reports_the_base_currency(client, seed_reporting):
    rows = client.get("/api/v1/reports/spend-by-category", headers=auth("tokA")).json()["rows"]
    assert rows[0]["currency"] == "DKK"
    assert float(rows[0]["amount_total"]) == 20.0
    assert rows[0]["unconverted_count"] == 0
