"""Low-confidence AI categorizations are flagged for review."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session

from web_api import config
from web_api.db.models import ErpEntry, InvoiceLine
from web_api_testkit import auth


@pytest.fixture()
def graded(engine, seed):
    """Four AI results across the confidence range, plus a verified one."""
    with Session(engine) as s:
        made = {}
        for name, status, confidence in (
            ("certain", "ai_categorized", Decimal("0.900")),
            ("borderline", "ai_categorized", Decimal("0.590")),
            ("doubtful", "ai_categorized", Decimal("0.200")),
            ("unscored", "ai_categorized", None),
            ("checked", "verified", Decimal("0.100")),
            ("broken", "ai_failed", None),
        ):
            line = InvoiceLine(
                company_id=seed["comp_a"], invoice_id=seed["inv_a"],
                item_name=name, amount=Decimal("10.00"), status=status,
                level_2="Technology", confidence=confidence,
            )
            s.add(line)
            s.commit()
            made[name] = line.id
        return made


def _names(client, query: str = "") -> set[str]:
    body = client.get(f"/api/v1/invoice-lines{query}", headers=auth("tokA")).json()
    return {item["item_name"] for item in body["items"] if item["item_name"]}


def test_doubtful_ai_lines_are_returned(client, graded):
    assert _names(client, "?needs_review=true") == {"doubtful", "borderline", "unscored"}


def test_a_confident_line_is_not_review_work(client, graded):
    assert "certain" not in _names(client, "?needs_review=true")


def test_a_verified_line_is_excluded_whatever_its_confidence(client, graded):
    assert "checked" not in _names(client, "?needs_review=true")


def test_failures_and_backlogs_are_not_folded_in(client, graded):
    returned = _names(client, "?needs_review=true")

    assert "broken" not in returned, "ai_failed is a fault, not a doubtful answer"
    assert "Cloud server" not in returned, "uncategorized is a backlog, not a review"


def test_an_unscored_ai_line_counts_as_doubtful(client, graded):
    assert "unscored" in _names(client, "?needs_review=true")


def test_false_returns_the_complement(client, graded):
    returned = _names(client, "?needs_review=false")

    assert "certain" in returned and "checked" in returned and "broken" in returned
    assert "doubtful" not in returned


def test_absent_leaves_the_listing_alone(client, graded):
    assert _names(client, "?needs_review=true") < _names(client)


def test_it_composes_with_the_other_filters(client, graded, seed):
    scoped = _names(client, f"?needs_review=true&company_id={seed['comp_a']}")
    assert scoped == {"doubtful", "borderline", "unscored"}

    other = client.get(
        f"/api/v1/invoice-lines?needs_review=true&company_id={seed['comp_b']}",
        headers=auth("tokA"),
    )
    assert other.status_code == 404, "another org's company is not the caller's to filter by"


def test_it_paginates(client, graded):
    body = client.get(
        "/api/v1/invoice-lines?needs_review=true&page_size=2", headers=auth("tokA")
    ).json()

    assert len(body["items"]) == 2
    assert body["total"] == 3


def test_the_flag_rides_on_every_line(client, graded):
    body = client.get("/api/v1/invoice-lines", headers=auth("tokA")).json()
    flags = {i["item_name"]: i["needs_review"] for i in body["items"] if i["item_name"]}

    assert flags["doubtful"] is True
    assert flags["certain"] is False
    assert flags["checked"] is False
    assert flags["broken"] is False


def test_raising_the_threshold_moves_history_without_rewriting_it(
    client, graded, engine, monkeypatch
):
    def flag_for(name: str) -> bool:
        body = client.get("/api/v1/invoice-lines", headers=auth("tokA")).json()
        return next(i["needs_review"] for i in body["items"] if i["item_name"] == name)

    assert flag_for("certain") is False

    monkeypatch.setattr(config, "CATEGORIZATION_REVIEW_THRESHOLD", 0.95)

    assert flag_for("certain") is True
    assert _names(client, "?needs_review=true") >= {"certain", "doubtful"}

    with Session(engine) as s:
        line = s.get(InvoiceLine, graded["certain"])
        assert line.confidence == Decimal("0.900"), "no row was rewritten"


def _vouchers(client, query: str = "") -> list[dict]:
    body = client.get(f"/api/v1/erp-entries/vouchers{query}", headers=auth("tokA")).json()
    return body["items"]


def test_a_voucher_holding_a_doubtful_line_is_returned(client, voucher_seed, engine):
    with Session(engine) as s:
        entry = s.get(ErpEntry, voucher_seed["entry_invoice"])
        s.add(InvoiceLine(
            company_id=entry.company_id, invoice_id=entry.source_invoice_id,
            item_name="doubtful", amount=Decimal("10.00"), status="ai_categorized",
            level_2="Technology", confidence=Decimal("0.200"),
        ))
        s.commit()
        voucher = entry.voucher_id

    returned = {v["voucher_id"] for v in _vouchers(client, "?needs_review=true")}

    assert voucher in returned


def test_a_voucher_whose_lines_are_all_confident_is_excluded(client, voucher_seed, engine):
    with Session(engine) as s:
        entry = s.get(ErpEntry, voucher_seed["entry_invoice"])
        s.add(InvoiceLine(
            company_id=entry.company_id, invoice_id=entry.source_invoice_id,
            item_name="certain", amount=Decimal("10.00"), status="ai_categorized",
            level_2="Technology", confidence=Decimal("0.950"),
        ))
        s.commit()

    assert _vouchers(client, "?needs_review=true") == []


def test_an_unlinked_posting_is_not_review_work_but_is_still_ordinary_work(
    client, voucher_seed, engine
):
    with_filter = {v["voucher_id"] for v in _vouchers(client, "?needs_review=true")}
    without = {v["voucher_id"] for v in _vouchers(client, "?needs_review=false")}
    unfiltered = {v["voucher_id"] for v in _vouchers(client)}

    assert with_filter == set()
    assert without == unfiltered, "the complement must lose nothing"


def test_the_flat_posting_list_has_no_such_filter(client, voucher_seed):
    res = client.get("/api/v1/erp-entries?needs_review=true", headers=auth("tokA"))

    assert res.status_code == 200
    assert len(res.json()["items"]) == len(
        client.get("/api/v1/erp-entries", headers=auth("tokA")).json()["items"]
    ), "an unknown query param is ignored, not honoured"
