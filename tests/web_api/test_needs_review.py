"""Low confidence is the review signal, now that the model may not decline.

The categorizer used to answer `0` when nothing fitted, which landed the line in
`ai_failed` — a red badge, no remedy named, and never retried. It now always
returns a category and records its doubt as a confidence. That is only an
improvement if the doubt is something a reviewer can select on, which is what
these pin.

The threshold is configuration, not a column, so the last test here is the one
that matters most: raising it has to move history without rewriting a row.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session

from web_api import config
from web_api.db.models import InvoiceLine

from .conftest import auth


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


# -- The filter ---------------------------------------------------------------


def test_doubtful_ai_lines_are_returned(client, graded):
    assert _names(client, "?needs_review=true") == {"doubtful", "borderline", "unscored"}


def test_a_confident_line_is_not_review_work(client, graded):
    assert "certain" not in _names(client, "?needs_review=true")


def test_a_verified_line_is_excluded_whatever_its_confidence(client, graded):
    """A person has already looked, which is the entire question the filter asks.
    `checked` sits at 0.1 — well under any threshold — and must not appear."""
    assert "checked" not in _names(client, "?needs_review=true")


def test_failures_and_backlogs_are_not_folded_in(client, graded):
    """They are separate work with their own filter. One filter meaning three
    kinds of task is a filter nobody can act on."""
    returned = _names(client, "?needs_review=true")

    assert "broken" not in returned, "ai_failed is a fault, not a doubtful answer"
    assert "Cloud server" not in returned, "uncategorized is a backlog, not a review"


def test_an_unscored_ai_line_counts_as_doubtful(client, graded):
    """A null confidence is not certainty. Every AI result carries one now, so a
    null means the line predates that — which is a reason to look, not to skip."""
    assert "unscored" in _names(client, "?needs_review=true")


def test_false_returns_the_complement(client, graded):
    returned = _names(client, "?needs_review=false")

    assert "certain" in returned and "checked" in returned and "broken" in returned
    assert "doubtful" not in returned


def test_absent_leaves_the_listing_alone(client, graded):
    assert _names(client, "?needs_review=true") < _names(client)


# -- Composition --------------------------------------------------------------


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


# -- The payload flag ---------------------------------------------------------


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
    """The reason this is configuration and not a column.

    A stored flag would be a snapshot of the setting at the moment the line was
    categorized — correct on the day and silently wrong for every row afterwards.
    """
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


# -- The voucher listing ------------------------------------------------------
#
# The Entries page lists vouchers and expands them into their invoice's lines,
# so this is where a reviewer actually meets the filter. It resolves through the
# *invoice*, not through the posting's own `source_invoice_line_id`: most
# postings carry no line link at all — input VAT, the payable and every journal
# entry belong to a voucher rather than to a line — so a line-linked filter would
# hide a doubtful line from the very voucher that displays it.


def _vouchers(client, query: str = "") -> list[dict]:
    body = client.get(f"/api/v1/erp-entries/vouchers{query}", headers=auth("tokA")).json()
    return body["items"]


def test_a_voucher_holding_a_doubtful_line_is_returned(client, voucher_seed, engine):
    from decimal import Decimal as D

    from web_api.db.models import ErpEntry

    with Session(engine) as s:
        entry = s.get(ErpEntry, voucher_seed["entry_invoice"])
        s.add(InvoiceLine(
            company_id=entry.company_id, invoice_id=entry.source_invoice_id,
            item_name="doubtful", amount=D("10.00"), status="ai_categorized",
            level_2="Technology", confidence=D("0.200"),
        ))
        s.commit()
        voucher = entry.voucher_id

    returned = {v["voucher_id"] for v in _vouchers(client, "?needs_review=true")}

    assert voucher in returned


def test_a_voucher_whose_lines_are_all_confident_is_excluded(client, voucher_seed, engine):
    from decimal import Decimal as D

    from web_api.db.models import ErpEntry

    with Session(engine) as s:
        entry = s.get(ErpEntry, voucher_seed["entry_invoice"])
        s.add(InvoiceLine(
            company_id=entry.company_id, invoice_id=entry.source_invoice_id,
            item_name="certain", amount=D("10.00"), status="ai_categorized",
            level_2="Technology", confidence=D("0.950"),
        ))
        s.commit()

    assert _vouchers(client, "?needs_review=true") == []


def test_an_unlinked_posting_is_not_review_work_but_is_still_ordinary_work(
    client, voucher_seed, engine
):
    """`NOT IN` over a NULL column yields NULL, which would drop unlinked
    postings from *both* answers — present in neither the filter nor its
    complement, and so invisible on a page that has the filter switched off."""
    with_filter = {v["voucher_id"] for v in _vouchers(client, "?needs_review=true")}
    without = {v["voucher_id"] for v in _vouchers(client, "?needs_review=false")}
    unfiltered = {v["voucher_id"] for v in _vouchers(client)}

    assert with_filter == set()
    assert without == unfiltered, "the complement must lose nothing"


def test_the_flat_posting_list_has_no_such_filter(client, voucher_seed):
    """A posting is the ledger's own record and carries no categorization. A
    line-derived filter on it would answer a question about something else."""
    res = client.get("/api/v1/erp-entries?needs_review=true", headers=auth("tokA"))

    assert res.status_code == 200
    assert len(res.json()["items"]) == len(
        client.get("/api/v1/erp-entries", headers=auth("tokA")).json()["items"]
    ), "an unknown query param is ignored, not honoured"
