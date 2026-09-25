"""ERP entry read endpoints: filters, pagination, tenant isolation."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from web_api.db.models import (
    Company,
    ErpAccount,
    ErpEntry,
    ErpIntegration,
    Invoice,
    InvoiceLine,
    Vendor,
)
from web_api_testkit import auth


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

        def ent(company_id, account_id, **kw):
            kw.setdefault("currency", "DKK")
            if "base_currency" not in kw:
                kw["base_currency"] = "DKK"
                kw["base_debit_amount"] = kw.get("debit_amount")
                kw["base_credit_amount"] = kw.get("credit_amount")
                kw["fx_rate"] = Decimal("1")
                kw["fx_rate_date"] = kw.get("accounting_date")
            row = ErpEntry(company_id=company_id, erp_account_id=account_id, **kw)
            s.add(row)
            return row

        a1 = ent(seed["comp_a"], acct_a.id, voucher_id="V1",
                 entry_type="purchase_invoice", source_invoice_id=seed["inv_a"],
                 accounting_date=date(2025, 7, 15), debit_amount=Decimal("80.00"),
                 status="pending")
        a2 = ent(seed["comp_a"], acct_a.id, voucher_id="V1",
                 entry_type="purchase_invoice", source_invoice_id=seed["inv_a"],
                 accounting_date=date(2025, 7, 15), debit_amount=Decimal("20.00"),
                 status="pending")
        a3 = ent(seed["comp_a"], acct_a.id, voucher_id="JE1",
                 entry_type="journal_entry", accounting_date=date(2025, 7, 20),
                 credit_amount=Decimal("100.00"), status="posted")
        b1 = ent(seed["comp_b"], acct_b.id, voucher_id="VB",
                 entry_type="purchase_invoice", source_invoice_id=seed["inv_b"],
                 accounting_date=date(2025, 8, 5), debit_amount=Decimal("50.00"), status="pending")
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
    journal = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                         params={"entry_type": "journal_entry"}).json()
    assert {e["id"] for e in journal["items"]} == {seed_entries["a3"]}


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


@pytest.fixture
def seed_deselected_account(engine, seed, seed_entries):
    """A voucher posted to an account the customer has switched off."""
    with Session(engine) as s:
        integration_id = s.exec(
            select(ErpAccount.erp_integration_id).where(ErpAccount.erp_account_code == "6010")
        ).one()
        vat = ErpAccount(erp_integration_id=integration_id, erp_account_code="2200",
                         erp_account_name="VAT Payable", erp_account_type="liability",
                         sync_enabled=False)
        s.add(vat)
        s.commit()
        row = ErpEntry(company_id=seed["comp_a"], erp_account_id=vat.id, voucher_id="V1",
                       entry_type="purchase_invoice", source_invoice_id=seed["inv_a"],
                       accounting_date=date(2025, 7, 15), debit_amount=Decimal("25.00"),
                       currency="DKK", base_currency="DKK",
                       base_debit_amount=Decimal("25.00"), fx_rate=Decimal("1"),
                       status="pending")
        s.add(row)
        s.commit()
        return {"account_id": vat.id, "entry_id": row.id}


def test_a_deselected_accounts_entries_are_not_listed(client, seed_entries, seed_deselected_account):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()
    assert seed_deselected_account["entry_id"] not in {e["id"] for e in body["items"]}
    assert body["total"] == len(body["items"]) == 3


def test_a_deselected_posting_is_absent_from_its_voucher_group(
    client, seed_entries, seed_deselected_account
):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    group = next(g for g in body["items"] if g["voucher_id"] == "V1")
    assert seed_deselected_account["entry_id"] not in {e["id"] for e in group["entries"]}
    assert group["entry_count"] == 2


def test_re_enabling_an_account_brings_its_entries_back(
    client, engine, seed_entries, seed_deselected_account
):
    with Session(engine) as s:
        account = s.get(ErpAccount, seed_deselected_account["account_id"])
        account.sync_enabled = True
        s.add(account)
        s.commit()

    body = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()
    assert seed_deselected_account["entry_id"] in {e["id"] for e in body["items"]}


def test_a_voucher_of_only_deselected_postings_yields_no_group(
    client, engine, seed, seed_entries, seed_deselected_account
):
    with Session(engine) as s:
        s.add(ErpEntry(company_id=seed["comp_a"],
                       erp_account_id=seed_deselected_account["account_id"],
                       voucher_id="OFF1", entry_type="purchase_invoice",
                       accounting_date=date(2025, 7, 21), debit_amount=Decimal("9.00"),
                       currency="DKK", status="pending"))
        s.commit()

    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    assert "OFF1" not in {g["voucher_id"] for g in body["items"]}


def test_a_deselected_entry_is_still_fetchable_by_id(
    client, seed_entries, seed_deselected_account
):
    r = client.get(f"/api/v1/erp-entries/{seed_deselected_account['entry_id']}",
                   headers=auth("tokA"))
    assert r.status_code == 200


@pytest.fixture
def seed_categorized_line(engine, seed, seed_entries):
    """One categorized invoice line, with **two** of Org A's postings on it."""
    with Session(engine) as s:
        line = InvoiceLine(
            company_id=seed["comp_a"], invoice_id=seed["inv_a"],
            description="Compliance advisory", amount=Decimal("100.00"),
            level_1="Indirect", level_2="Legal", level_3="Professional Services",
        )
        s.add(line)
        s.commit()
        for eid in (seed_entries["a1"], seed_entries["a2"]):
            row = s.get(ErpEntry, eid)
            row.source_invoice_line_id = line.id
            s.add(row)
        s.commit()
        return line.id


def test_a_posting_reports_its_lines_category(client, seed_entries, seed_categorized_line):
    body = client.get(f"/api/v1/erp-entries/{seed_entries['a1']}", headers=auth("tokA")).json()
    assert body["source_invoice_line_id"] == seed_categorized_line
    assert body["spend_category_level_1"] == "Indirect"
    assert body["spend_category_level_2"] == "Legal"
    assert body["spend_category_level_3"] == "Professional Services"


def test_several_postings_share_one_lines_category(client, seed_entries, seed_categorized_line):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()
    by_id = {e["id"]: e for e in body["items"]}
    for eid in (seed_entries["a1"], seed_entries["a2"]):
        assert by_id[eid]["spend_category_level_2"] == "Legal"
        assert by_id[eid]["source_invoice_line_id"] == seed_categorized_line


def test_a_posting_with_no_line_reports_no_category(client, seed_entries, seed_categorized_line):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()
    unlinked = next(e for e in body["items"] if e["id"] == seed_entries["a3"])
    assert unlinked["source_invoice_line_id"] is None
    assert unlinked["spend_category_level_1"] is None
    assert unlinked["spend_category_level_2"] is None


def test_an_uncategorized_line_reports_no_category(client, engine, seed, seed_entries):
    with Session(engine) as s:
        line = InvoiceLine(company_id=seed["comp_a"], invoice_id=seed["inv_a"],
                           description="Not yet categorized", amount=Decimal("10.00"))
        s.add(line)
        s.commit()
        row = s.get(ErpEntry, seed_entries["a1"])
        row.source_invoice_line_id = line.id
        s.add(row)
        s.commit()
        line_id = line.id

    body = client.get(f"/api/v1/erp-entries/{seed_entries['a1']}", headers=auth("tokA")).json()
    assert body["source_invoice_line_id"] == line_id
    assert body["spend_category_level_2"] is None


def test_the_voucher_groups_carry_the_category_too(client, seed_entries, seed_categorized_line):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    group = next(g for g in body["items"] if g["voucher_id"] == "V1")
    linked = next(e for e in group["entries"] if e["id"] == seed_entries["a1"])
    assert linked["spend_category_level_2"] == "Legal"


@pytest.fixture
def seed_interleaved(engine, seed, seed_entries):
    """Two vouchers posted the same day, plus an undated posting."""
    with Session(engine) as s:
        account_id = s.exec(select(ErpEntry.erp_account_id).where(
            ErpEntry.company_id == seed["comp_a"])).first()
        for row_id, voucher, day in [
            ("ord-1", "X", date(2025, 9, 1)),
            ("ord-2", "Y", date(2025, 9, 1)),
            ("ord-3", "X", date(2025, 9, 1)),
            ("ord-4", "Y", date(2025, 9, 1)),
            ("ord-5", None, None),
        ]:
            s.add(ErpEntry(
                id=row_id, company_id=seed["comp_a"], erp_account_id=account_id,
                voucher_id=voucher, entry_type="purchase_invoice",
                accounting_date=day, debit_amount=Decimal("10.00"),
                currency="DKK", status="pending",
            ))
        s.commit()


def test_a_vouchers_postings_stay_adjacent(client, seed_interleaved):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                      params={"from": "2025-09-01", "to": "2025-09-01"}).json()
    assert [e["voucher_id"] for e in body["items"]] == ["X", "X", "Y", "Y"]


def test_undated_entries_sort_last(client, seed_interleaved):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()
    dates = [e["accounting_date"] for e in body["items"]]
    assert dates[-1] is None
    assert None not in dates[:-1]
    assert dates[:-1] == sorted((d for d in dates if d is not None), reverse=True)


def test_detail_in_scope(client, seed_entries):
    r = client.get(f"/api/v1/erp-entries/{seed_entries['a1']}", headers=auth("tokA"))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == seed_entries["a1"]
    assert body["voucher_id"] == "V1"
    assert body["entry_type"] == "purchase_invoice"
    assert body["accounting_date"] == "2025-07-15"
    assert "erp_integration_id" not in body
    assert "gt_account_code" not in body
    assert "gt_level_1" not in body
    assert "raw_json" not in body


def test_detail_cross_tenant_is_404(client, seed_entries):
    r = client.get(f"/api/v1/erp-entries/{seed_entries['a1']}", headers=auth("tokB"))
    assert r.status_code == 404


def test_detail_unknown_is_404(client, seed_entries):
    r = client.get("/api/v1/erp-entries/does-not-exist", headers=auth("tokA"))
    assert r.status_code == 404


@pytest.fixture
def seed_extra(engine, seed, seed_entries):
    """Additive scenarios layered on `seed_entries`, so the base counts hold."""
    ids: dict[str, str] = {}
    with Session(engine) as s:
        vendor = Vendor(name="Contoso ApS", vat_number="DK12345678")
        s.add(vendor)
        s.commit()
        inv_a = s.get(Invoice, seed["inv_a"])
        inv_a.vendor_id = vendor.id
        s.add(inv_a)

        acct_a = s.exec(
            select(ErpAccount).join(
                ErpIntegration, ErpIntegration.id == ErpAccount.erp_integration_id
            ).where(ErpIntegration.company_id == seed["comp_a"])
        ).first()
        acct_b = s.exec(
            select(ErpAccount).join(
                ErpIntegration, ErpIntegration.id == ErpAccount.erp_integration_id
            ).where(ErpIntegration.company_id == seed["comp_b"])
        ).first()

        nodate = ErpEntry(company_id=seed["comp_a"], erp_account_id=acct_a.id,
                          entry_type="adjustment", status="failed",
                          error_message="ERP rejected the posting",
                          debit_amount=Decimal("5.00"))
        mix1 = ErpEntry(company_id=seed["comp_a"], erp_account_id=acct_a.id,
                        voucher_id="VMIX", entry_type="journal",
                        accounting_date=date(2025, 6, 1), currency="DKK",
                        debit_amount=Decimal("10.00"), status="pending")
        mix2 = ErpEntry(company_id=seed["comp_a"], erp_account_id=acct_a.id,
                        voucher_id="VMIX", entry_type="journal",
                        accounting_date=date(2025, 6, 1), currency="EUR",
                        debit_amount=Decimal("20.00"), status="pending")
        collide = ErpEntry(company_id=seed["comp_b"], erp_account_id=acct_b.id,
                           voucher_id="V1", entry_type="purchase_invoice",
                           accounting_date=date(2025, 8, 9),
                           debit_amount=Decimal("7.00"), status="pending")
        for row in (nodate, mix1, mix2, collide):
            s.add(row)
        s.commit()
        ids = {"vendor": vendor.id, "nodate": nodate.id, "mix1": mix1.id,
               "mix2": mix2.id, "collide": collide.id}
    return ids


def test_list_resolves_account_code_and_name(client, seed_entries):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()
    assert all(e["erp_account_code"] == "6010" for e in body["items"])
    assert all(e["erp_account_name"] == "Cloud Hosting" for e in body["items"])


def test_detail_resolves_account_code_and_name(client, seed_entries):
    body = client.get(f"/api/v1/erp-entries/{seed_entries['a1']}", headers=auth("tokA")).json()
    assert body["erp_account_code"] == "6010"
    assert body["erp_account_name"] == "Cloud Hosting"


def test_vendor_resolved_through_source_invoice(client, seed_entries, seed_extra):
    body = client.get(f"/api/v1/erp-entries/{seed_entries['a1']}", headers=auth("tokA")).json()
    assert body["vendor_id"] == seed_extra["vendor"]
    assert body["vendor_name"] == "Contoso ApS"


def test_vendor_is_null_for_unlinked_entry(client, seed_entries, seed_extra):
    body = client.get(f"/api/v1/erp-entries/{seed_entries['a3']}", headers=auth("tokA")).json()
    assert body["vendor_id"] is None
    assert body["vendor_name"] is None


def test_error_message_is_exposed(client, seed_extra):
    body = client.get(f"/api/v1/erp-entries/{seed_extra['nodate']}", headers=auth("tokA")).json()
    assert body["status"] == "failed"
    assert body["error_message"] == "ERP rejected the posting"


def test_filter_by_date_range_is_inclusive(client, seed_entries):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                      params={"from": "2025-07-15", "to": "2025-07-15"}).json()
    assert {e["id"] for e in body["items"]} == {seed_entries["a1"], seed_entries["a2"]}

    wider = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                       params={"from": "2025-07-15", "to": "2025-07-20"}).json()
    assert wider["total"] == 3


def test_date_range_excludes_undated_entries(client, seed_entries, seed_extra):
    unfiltered = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()
    assert seed_extra["nodate"] in {e["id"] for e in unfiltered["items"]}

    ranged = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                        params={"from": "2020-01-01", "to": "2030-01-01"}).json()
    assert seed_extra["nodate"] not in {e["id"] for e in ranged["items"]}


def test_filter_by_vendor_excludes_unlinked_entries(client, seed_entries, seed_extra):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                      params={"vendor_id": seed_extra["vendor"]}).json()
    assert {e["id"] for e in body["items"]} == {seed_entries["a1"], seed_entries["a2"]}
    assert seed_entries["a3"] not in {e["id"] for e in body["items"]}


def test_vendor_filter_composes_with_others(client, seed_entries, seed_extra):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                      params={"vendor_id": seed_extra["vendor"], "status": "posted"}).json()
    assert body["total"] == 0


def test_voucher_group_bundles_a_voucher_postings(client, seed_entries):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    groups = {g["voucher_id"]: g for g in body["items"]}
    v1 = groups["V1"]
    assert v1["entry_count"] == 2
    assert {e["id"] for e in v1["entries"]} == {seed_entries["a1"], seed_entries["a2"]}
    assert Decimal(v1["debit_total"]) == Decimal("100.00")
    assert Decimal(v1["credit_total"]) == Decimal("0")
    assert v1["accounting_date"] == "2025-07-15"
    assert v1["entry_types"] == ["purchase_invoice"]


def test_voucher_groups_carry_the_shared_supplier(client, seed_entries, seed_extra):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    v1 = next(g for g in body["items"] if g["voucher_id"] == "V1")
    assert v1["vendor_name"] == "Contoso ApS"


def test_voucher_pagination_never_splits_a_voucher(client, seed_entries):
    first = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"),
                       params={"page_size": 1, "page": 1}).json()
    assert first["total"] == 2
    assert len(first["items"]) == 1
    seen = {g["voucher_id"]: g for g in first["items"]}

    second = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"),
                        params={"page_size": 1, "page": 2}).json()
    seen.update({g["voucher_id"]: g for g in second["items"]})
    assert set(seen) == {"V1", "JE1"}
    assert seen["V1"]["entry_count"] == 2
    assert len(seen["V1"]["entries"]) == 2


def test_voucherless_entry_forms_its_own_group(client, seed_entries, seed_extra):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    solo = [g for g in body["items"] if g["voucher_id"] is None]
    assert len(solo) == 1
    assert solo[0]["entry_count"] == 1
    assert solo[0]["entries"][0]["id"] == seed_extra["nodate"]


def test_mixed_currency_group_reports_null_currency(client, seed_entries, seed_extra):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    mixed = next(g for g in body["items"] if g["voucher_id"] == "VMIX")
    assert mixed["currency"] is None
    assert mixed["entry_count"] == 2


def test_voucher_filters_apply_before_grouping(client, seed_entries, seed_extra):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"),
                      params={"status": "failed"}).json()
    assert body["total"] == 1
    assert body["items"][0]["entries"][0]["id"] == seed_extra["nodate"]

    ranged = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"),
                        params={"from": "2025-07-01"}).json()
    assert {g["voucher_id"] for g in ranged["items"]} == {"V1", "JE1"}


def test_voucher_groups_do_not_merge_across_tenants(client, seed_entries, seed_extra):
    a = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    a_v1 = next(g for g in a["items"] if g["voucher_id"] == "V1")
    assert a_v1["entry_count"] == 2
    assert seed_extra["collide"] not in {e["id"] for e in a_v1["entries"]}

    b = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokB")).json()
    b_v1 = next(g for g in b["items"] if g["voucher_id"] == "V1")
    assert {e["id"] for e in b_v1["entries"]} == {seed_extra["collide"]}


def test_undated_group_sorts_last(client, seed_entries, seed_extra):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    order = [g["voucher_id"] for g in body["items"]]
    assert order == ["JE1", "V1", "VMIX", None]


def test_voucher_empty_scope_returns_empty_page(client, seed_entries):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tok_empty")).json()
    assert body == {"items": [], "page": 1, "page_size": 25, "total": 0}


def test_vouchers_path_is_not_swallowed_by_the_detail_route(client, seed_entries):
    r = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"))
    assert r.status_code == 200
    assert "items" in r.json()


@pytest.fixture
def seed_typed_accounts(engine, seed):
    """A realistic purchase voucher: net expense + VAT debit, payable credit."""
    ids: dict[str, str] = {}
    with Session(engine) as s:
        intg = ErpIntegration(company_id=seed["comp_a"], erp_type="mock")
        s.add(intg)
        s.commit()
        expense = ErpAccount(erp_integration_id=intg.id, erp_account_code="6020",
                             erp_account_name="Software Subscriptions",
                             erp_account_type="expense")
        vat = ErpAccount(erp_integration_id=intg.id, erp_account_code="2200",
                         erp_account_name="VAT Payable", erp_account_type="liability")
        payable = ErpAccount(erp_integration_id=intg.id, erp_account_code="2100",
                             erp_account_name="Accounts Payable", erp_account_type="liability")
        bank = ErpAccount(erp_integration_id=intg.id, erp_account_code="1000",
                          erp_account_name="Cash", erp_account_type="asset")
        for a in (expense, vat, payable, bank):
            s.add(a)
        s.commit()

        def ent(acct, **kw):
            if "base_currency" not in kw:
                kw["base_currency"] = "DKK"
                kw["base_debit_amount"] = kw.get("debit_amount")
                kw["base_credit_amount"] = kw.get("credit_amount")
                kw["fx_rate"] = Decimal("1")
                kw["fx_rate_date"] = kw.get("accounting_date")
            row = ErpEntry(company_id=seed["comp_a"], erp_account_id=acct.id, **kw)
            s.add(row)
            return row

        ent(expense, voucher_id="P1", entry_type="purchase_invoice",
            accounting_date=date(2026, 5, 1), debit_amount=Decimal("21658.04"),
            currency="DKK", status="pending")
        ent(vat, voucher_id="P1", entry_type="purchase_invoice",
            accounting_date=date(2026, 5, 1), debit_amount=Decimal("5414.51"),
            currency="DKK", status="pending")
        ent(payable, voucher_id="P1", entry_type="purchase_invoice",
            accounting_date=date(2026, 5, 1), credit_amount=Decimal("27072.55"),
            currency="DKK", status="pending")
        ent(expense, voucher_id="CN1", entry_type="credit_note",
            accounting_date=date(2026, 5, 4), credit_amount=Decimal("3200.00"),
            currency="DKK", status="pending")
        ent(payable, voucher_id="CN1", entry_type="credit_note",
            accounting_date=date(2026, 5, 4), debit_amount=Decimal("3200.00"),
            currency="DKK", status="pending")
        ent(payable, voucher_id="PAY1", entry_type="payment",
            accounting_date=date(2026, 5, 9), debit_amount=Decimal("27072.55"),
            currency="DKK", status="pending")
        ent(bank, voucher_id="PAY1", entry_type="payment",
            accounting_date=date(2026, 5, 9), credit_amount=Decimal("27072.55"),
            currency="DKK", status="pending")
        ent(payable, voucher_id="JE9", entry_type="journal_entry",
            accounting_date=date(2026, 5, 11), debit_amount=Decimal("40.00"),
            currency="DKK", status="pending")
        ent(bank, voucher_id="JE9", entry_type="journal_entry",
            accounting_date=date(2026, 5, 11), credit_amount=Decimal("40.00"),
            currency="DKK", status="pending")
        s.commit()
        ids = {"expense": expense.id, "payable": payable.id}
    return ids


def _groups(client, token="tokA"):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth(token)).json()
    return {g["voucher_id"]: g for g in body["items"]}


def test_amount_is_net_spend_excluding_vat_and_payable(client, seed_typed_accounts):
    purchase = _groups(client)["P1"]
    assert Decimal(purchase["amount"]) == Decimal("21658.04")
    assert Decimal(purchase["debit_total"]) == Decimal("27072.55")
    assert Decimal(purchase["credit_total"]) == Decimal("27072.55")


def test_debit_minus_credit_would_have_been_zero(client, seed_typed_accounts):
    purchase = _groups(client)["P1"]
    assert Decimal(purchase["debit_total"]) - Decimal(purchase["credit_total"]) == Decimal("0")
    assert Decimal(purchase["amount"]) != Decimal("0")


def test_a_refund_is_negative_spend(client, seed_typed_accounts):
    refund = _groups(client)["CN1"]
    assert Decimal(refund["amount"]) == Decimal("-3200.00")


def test_a_voucher_that_spent_nothing_has_no_amount(client, seed_typed_accounts):
    assert _groups(client)["JE9"]["amount"] is None


def test_payments_are_absent_from_the_voucher_groups(client, seed_typed_accounts):
    groups = _groups(client)
    assert "PAY1" not in groups
    assert {"P1", "CN1", "JE9"} <= set(groups)


def test_payments_are_absent_from_the_flat_list(client, seed_typed_accounts):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()
    assert "payment" not in {e["entry_type"] for e in body["items"]}
    assert body["total"] == len(body["items"])


def test_asking_for_payments_returns_nothing_rather_than_overriding(client, seed_typed_accounts):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA"),
                      params={"entry_type": "payment"}).json()
    assert body["total"] == 0
    assert body["items"] == []


def test_a_credit_note_is_kept(client, seed_typed_accounts):
    assert Decimal(_groups(client)["CN1"]["amount"]) == Decimal("-3200.00")


def test_amount_falls_back_when_the_connector_declares_no_types(client, seed_entries):
    v1 = _groups(client)["V1"]
    assert Decimal(v1["amount"]) == Decimal(v1["debit_total"]) == Decimal("100.00")


@pytest.fixture
def mixed_currency_voucher(engine, seed, seed_entries):
    """One voucher posted in EUR and USD, both converted into the company's DKK."""
    with Session(engine) as s:
        account = s.exec(select(ErpAccount)).first()

        def posting(currency, amount, rate):
            s.add(ErpEntry(
                company_id=seed["comp_a"], erp_account_id=account.id,
                voucher_id="MIX", entry_type="purchase_invoice",
                accounting_date=date(2026, 2, 2), currency=currency,
                debit_amount=amount, status="pending",
                base_currency="DKK", fx_rate=rate, fx_rate_date=date(2026, 2, 2),
                base_debit_amount=(amount * rate).quantize(Decimal("0.01")),
            ))

        posting("EUR", Decimal("100.00"), Decimal("7.46"))
        posting("USD", Decimal("100.00"), Decimal("6.88"))
        s.commit()


def _voucher(client, voucher_id, **params):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"),
                      params=params).json()
    return next(g for g in body["items"] if g["voucher_id"] == voucher_id)


def test_a_mixed_currency_voucher_gets_one_base_total(client, mixed_currency_voucher):
    group = _voucher(client, "MIX")

    assert group["currency"] == "DKK"
    assert Decimal(group["debit_total"]) == Decimal("1434.00")
    assert group["unconverted_count"] == 0


def test_original_mode_still_refuses_to_combine_them(client, mixed_currency_voucher):
    group = _voucher(client, "MIX", currency_mode="original")

    assert group["currency"] is None
    assert Decimal(group["debit_total"]) == Decimal("200.00")


def test_an_entry_carries_both_figures_in_either_mode(client, mixed_currency_voucher):
    for mode in ("base", "original"):
        entry = _voucher(client, "MIX", currency_mode=mode)["entries"][0]
        assert entry["currency"] in {"EUR", "USD"}
        assert entry["base_currency"] == "DKK"
        assert Decimal(entry["fx_rate"]) > 0
        assert entry["fx_rate_date"] == "2026-02-02"


def test_an_unconverted_posting_is_counted_not_folded_in(client, engine, seed, seed_entries):
    with Session(engine) as s:
        account = s.exec(select(ErpAccount)).first()
        s.add(ErpEntry(company_id=seed["comp_a"], erp_account_id=account.id,
                       voucher_id="V1", entry_type="purchase_invoice",
                       accounting_date=date(2025, 7, 15), currency="GBP",
                       debit_amount=Decimal("500.00"), status="pending"))
        s.commit()

    group = _voucher(client, "V1")

    assert group["unconverted_count"] == 1
    assert Decimal(group["debit_total"]) == Decimal("100.00")
    assert group["currency"] == "DKK"


def test_a_wholly_unconverted_voucher_reports_no_total(client, engine, seed, seed_entries):
    with Session(engine) as s:
        for entry in s.exec(select(ErpEntry).where(ErpEntry.voucher_id == "V1")).all():
            entry.base_currency = None
            entry.base_debit_amount = None
            entry.fx_rate = None
            s.add(entry)
        s.commit()

    group = _voucher(client, "V1")

    assert group["debit_total"] is None
    assert group["amount"] is None
    assert group["currency"] is None
    assert group["unconverted_count"] == 2


def test_an_unknown_currency_mode_is_rejected(client, seed_entries):
    r = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA"),
                   params={"currency_mode": "usd"})
    assert r.status_code == 422


def test_the_entry_detail_endpoint_carries_the_conversion(client, seed_entries):
    body = client.get(f"/api/v1/erp-entries/{seed_entries['a1']}", headers=auth("tokA")).json()

    assert body["base_currency"] == "DKK"
    assert Decimal(body["base_debit_amount"]) == Decimal("80.00")
    assert Decimal(body["fx_rate"]) == Decimal("1")


@pytest.fixture
def deactivated_company(engine, seed, seed_entries):
    """A second company in Org A, deactivated, carrying one entry of its own."""

    with Session(engine) as s:
        company = Company(organization_id=s.get(Company, seed["comp_a"]).organization_id,
                          name="Retired Co", base_currency="DKK", is_active=False)
        s.add(company)
        s.commit()
        integration = ErpIntegration(company_id=company.id, erp_type="mock")
        s.add(integration)
        s.commit()
        account = ErpAccount(erp_integration_id=integration.id,
                             erp_account_code="7010", erp_account_name="Old Costs")
        s.add(account)
        s.commit()
        entry = ErpEntry(
            company_id=company.id, erp_account_id=account.id, voucher_id="RET-1",
            erp_entry_id="RET-1-1", entry_type="purchase_invoice",
            accounting_date=date(2025, 7, 9), debit_amount=Decimal("999.00"),
            currency="DKK", base_currency="DKK", base_debit_amount=Decimal("999.00"),
            fx_rate=Decimal("1"), fx_rate_date=date(2025, 7, 9),
        )
        s.add(entry)
        s.commit()
        return {"company_id": company.id, "entry_id": entry.id, "voucher_id": "RET-1"}


def test_all_companies_excludes_a_deactivated_company(client, deactivated_company):
    body = client.get("/api/v1/erp-entries", headers=auth("tokA")).json()

    assert deactivated_company["company_id"] not in {r["company_id"] for r in body["items"]}
    assert body["items"], "the active company's entries must still be listed"


def test_voucher_groups_agree_with_the_flat_list(client, deactivated_company):
    body = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    assert deactivated_company["voucher_id"] not in {g["voucher_id"] for g in body["items"]}


def test_asking_for_the_deactivated_company_by_id_still_works(client, deactivated_company):
    body = client.get(
        "/api/v1/erp-entries",
        params={"company_id": deactivated_company["company_id"]},
        headers=auth("tokA"),
    ).json()

    assert [r["company_id"] for r in body["items"]] == [deactivated_company["company_id"]]


def test_a_single_entry_of_a_deactivated_company_is_still_readable(client, deactivated_company):
    r = client.get(f"/api/v1/erp-entries/{deactivated_company['entry_id']}",
                   headers=auth("tokA"))
    assert r.status_code == 200


def test_reports_exclude_a_deactivated_company_too(client, seed, deactivated_company):
    def totals(**params):
        rows = client.get("/api/v1/reports/entries-summary", params=params,
                          headers=auth("tokA")).json()["rows"]
        return {(r["entry_type"], r["currency"]): Decimal(str(r["debit_total"])) for r in rows}

    org_wide = totals()
    active_only = totals(company_id=seed["comp_a"])
    retired = totals(company_id=deactivated_company["company_id"])

    assert retired, "the deactivated company must have figures of its own to leak"
    assert org_wide == active_only


def test_the_voucher_panel_reports_whether_its_lines_add_up(client, voucher_seed, engine):
    body = client.get(
        f"/api/v1/erp-entries/vouchers/{voucher_seed["voucher"]}", headers=auth("tokA")
    ).json()
    assert body["invoice"]["lines_reconciled"] is True

    with Session(engine) as s:
        invoice = s.get(Invoice, body["invoice"]["id"])
        invoice.total = Decimal("99999.00")
        s.add(invoice)
        s.commit()

    body = client.get(
        f"/api/v1/erp-entries/vouchers/{voucher_seed["voucher"]}", headers=auth("tokA")
    ).json()
    assert body["invoice"]["lines_reconciled"] is False
    assert body["invoice"]["reconciliation_delta"] is not None
