"""One-request voucher detail endpoint: postings + invoice + document."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlmodel import Session

from web_api.audit import record_audit
from web_api.db.models import AuditLog, ErpAccount, ErpEntry

from web_api_testkit import auth


@pytest.fixture
def eur_voucher(engine, voucher_seed):
    """A voucher posted in EUR, converted to the company's DKK base."""
    with Session(engine) as s:
        entry = ErpEntry(
            company_id=voucher_seed["comp_a"], erp_account_id=voucher_seed["account_a"],
            voucher_id="EUR1", entry_type="purchase_invoice",
            accounting_date=date(2025, 7, 10), currency="EUR",
            debit_amount=Decimal("100.00"), status="pending",
            base_currency="DKK", fx_rate=Decimal("7.46"), fx_rate_date=date(2025, 7, 10),
            base_debit_amount=Decimal("746.00"),
        )
        s.add(entry)
        s.commit()
        return {"voucher_id": "EUR1", "entry_id": entry.id}


def test_voucher_detail_defaults_to_the_base_currency_total(client, voucher_seed, eur_voucher):
    body = client.get(f"/api/v1/erp-entries/vouchers/{eur_voucher['voucher_id']}",
                      headers=auth("tokA")).json()

    assert body["currency"] == "DKK"
    assert Decimal(body["amount"]) == Decimal("746.00")


def test_voucher_detail_original_mode_reports_the_as_posted_figure(
    client, voucher_seed, eur_voucher
):
    body = client.get(f"/api/v1/erp-entries/vouchers/{eur_voucher['voucher_id']}",
                      headers=auth("tokA"), params={"currency_mode": "original"}).json()

    assert body["currency"] == "EUR"
    assert Decimal(body["amount"]) == Decimal("100.00")


def test_voucher_detail_amount_matches_the_voucher_groups_total(
    client, voucher_seed, eur_voucher
):
    detail = client.get(f"/api/v1/erp-entries/vouchers/{eur_voucher['voucher_id']}",
                        headers=auth("tokA")).json()
    groups = client.get("/api/v1/erp-entries/vouchers", headers=auth("tokA")).json()
    group = next(g for g in groups["items"] if g["voucher_id"] == eur_voucher["voucher_id"])

    assert detail["amount"] == group["amount"]
    assert detail["currency"] == group["currency"]


def test_by_entry_detail_also_defaults_to_base_currency(client, voucher_seed, eur_voucher):
    body = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{eur_voucher['entry_id']}",
        headers=auth("tokA"),
    ).json()

    assert body["currency"] == "DKK"
    assert Decimal(body["amount"]) == Decimal("746.00")


def test_voucher_audit_still_works_when_the_voucher_needs_conversion(
    client, voucher_seed, eur_voucher
):
    res = client.get(f"/api/v1/erp-entries/vouchers/{eur_voucher['voucher_id']}/audit",
                     headers=auth("tokA"))
    assert res.status_code == 200


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


def test_voucher_audit_merges_invoice_and_line_rows_newest_first(client, voucher_seed):
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
    assert all(r["entity_label"] for r in rows)


def test_voucher_audit_by_entry_matches_direct_lookup(client, voucher_seed):
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
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{voucher_seed['entry_unvouchered']}/audit",
        headers=auth("tokA"),
    )
    assert res.status_code == 200
    assert res.json() == []


def test_voucher_audit_is_tenant_scoped(client, voucher_seed):
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
        assert row1.created_at == row2.created_at
        assert row1.seq < row2.seq
        expected_order = [row2.id, row1.id]

    first = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}/audit",
                       headers=auth("tokA")).json()
    second = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}/audit",
                        headers=auth("tokA")).json()

    assert [r["id"] for r in first] == expected_order
    assert [r["id"] for r in second] == expected_order


def test_record_audit_twice_in_one_flush_assigns_distinct_seq(engine, voucher_seed):
    with Session(engine) as s:
        row1 = record_audit(s, entity_type="invoice_line", entity_id=voucher_seed["line_a1"],
                            action="ai_categorize", actor="system", changes=[])
        row2 = record_audit(s, entity_type="invoice_line", entity_id=voucher_seed["line_a2"],
                            action="ai_categorize", actor="system", changes=[])
        s.commit()

        assert row1.seq is not None
        assert row2.seq is not None
        assert row1.seq != row2.seq
        assert row1.seq < row2.seq


@pytest.fixture
def deselected_posting(engine, voucher_seed):
    """A second posting on voucher "4821", on an account switched off from sync."""
    with Session(engine) as s:
        disabled = ErpAccount(
            erp_integration_id=voucher_seed["integration_a"],
            erp_account_code="6300", erp_account_name="Deselected Software",
            erp_account_type="expense", sync_enabled=False,
        )
        s.add(disabled)
        s.commit()
        entry = ErpEntry(
            company_id=voucher_seed["comp_a"], erp_account_id=disabled.id,
            voucher_id="4821", entry_type="credit_note",
            accounting_date=date(2025, 7, 3),
            debit_amount=Decimal("15.00"), currency="DKK",
        )
        s.add(entry)
        s.commit()
        return {"account_id": disabled.id, "entry_id": entry.id}


@pytest.fixture
def all_deselected_voucher(engine, voucher_seed):
    """A voucher whose only posting is on a deselected account — nothing about it is visible once `sync_enabled` is honoured."""
    with Session(engine) as s:
        disabled = ErpAccount(
            erp_integration_id=voucher_seed["integration_a"],
            erp_account_code="6400", erp_account_name="Fully Deselected",
            erp_account_type="expense", sync_enabled=False,
        )
        s.add(disabled)
        s.commit()
        entry = ErpEntry(
            company_id=voucher_seed["comp_a"], erp_account_id=disabled.id,
            voucher_id="OFF1", entry_type="purchase_invoice",
            accounting_date=date(2025, 7, 4),
            debit_amount=Decimal("30.00"), currency="DKK",
        )
        s.add(entry)
        s.commit()
        return {"voucher_id": "OFF1", "entry_id": entry.id}


def test_voucher_detail_hides_a_deselected_accounts_posting(
    client, voucher_seed, deselected_posting
):
    body = client.get("/api/v1/erp-entries/vouchers/4821", headers=auth("tokA")).json()

    assert body["entry_count"] == 2
    assert deselected_posting["entry_id"] not in {e["id"] for e in body["entries"]}


def test_voucher_of_only_deselected_postings_is_404(
    client, voucher_seed, all_deselected_voucher
):
    res = client.get(
        f"/api/v1/erp-entries/vouchers/{all_deselected_voucher['voucher_id']}",
        headers=auth("tokA"),
    )
    assert res.status_code == 404


def test_by_entry_addressed_at_a_deselected_posting_is_404(
    client, voucher_seed, deselected_posting
):
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{deselected_posting['entry_id']}",
        headers=auth("tokA"),
    )
    assert res.status_code == 404


def test_by_entry_at_the_only_posting_of_an_all_deselected_voucher_is_404(
    client, voucher_seed, all_deselected_voucher
):
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{all_deselected_voucher['entry_id']}",
        headers=auth("tokA"),
    )
    assert res.status_code == 404


def test_voucher_audit_of_only_deselected_postings_is_404(
    client, voucher_seed, all_deselected_voucher
):
    res = client.get(
        f"/api/v1/erp-entries/vouchers/{all_deselected_voucher['voucher_id']}/audit",
        headers=auth("tokA"),
    )
    assert res.status_code == 404


def test_voucher_audit_by_entry_of_a_deselected_posting_is_404(
    client, voucher_seed, deselected_posting
):
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{deselected_posting['entry_id']}/audit",
        headers=auth("tokA"),
    )
    assert res.status_code == 404


def test_voucher_on_enabled_accounts_is_unaffected_by_a_sibling_deselection(
    client, voucher_seed, deselected_posting
):
    res = client.get("/api/v1/erp-entries/vouchers/by-entry/"
                     f"{voucher_seed['entry_unvouchered']}", headers=auth("tokA"))
    assert res.status_code == 200
    assert res.json()["entry_count"] == 1
