"""The API for categories a tree is missing.

The load-bearing property is negative: accepting a suggestion must create the
node through `spend_trees/service.py` like any other node, never by writing the
table. That service is the only thing that keeps `parent_id` and the
materialized `level_*` path in step, and a suggestion that bypassed it would
produce a node whose path resolves to nothing — exactly the stale state the
stored pointer exists to prevent.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session, select

from web_api.db.models import (
    Company, Invoice, InvoiceLine, SpendCategory, SpendCategorySuggestion,
    SuggestionState, Vendor,
)
from web_api.spend_trees import service

from .conftest import auth


@pytest.fixture()
def tree_with_suggestion(engine, seed):
    with Session(engine) as s:
        tree = service.create_tree(s, seed["org_a"], "Sparse", max_depth=3)
        root = service.add_node(s, tree, "Indirect")
        travel = service.add_node(s, tree, "Travel & Entertainment", parent_id=root.id)
        service.add_node(s, tree, "Airfare", parent_id=travel.id)
        s.commit()

        company = s.get(Company, seed["comp_a"])
        company.spend_tree_id = tree.id
        s.add(company)

        vendor = Vendor(name="DSB")
        s.add(vendor)
        s.commit()
        invoice = Invoice(company_id=company.id, vendor_id=vendor.id,
                          currency="DKK", status="uncategorized")
        s.add(invoice)
        s.commit()
        line = InvoiceLine(
            company_id=company.id, invoice_id=invoice.id, item_name="Togbillet",
            amount=Decimal("58.00"), status="ai_categorized",
            level_3="Airfare", confidence=Decimal("0.200"),
        )
        s.add(line)
        s.commit()

        suggestion = SpendCategorySuggestion(
            spend_tree_id=tree.id, company_id=company.id, parent_id=travel.id,
            name="Ground Transport", description="Rail, bus and taxi.",
            rationale="Rail travel has no home in this tree.",
            evidence_line_ids=[line.id],
        )
        s.add(suggestion)
        s.commit()
        return {
            "tree": tree.id, "suggestion": suggestion.id,
            "parent": travel.id, "line": line.id,
        }


def _list(client, tree_id: str, token: str = "tokA", query: str = ""):
    return client.get(
        f"/api/v1/spend-trees/{tree_id}/suggestions{query}", headers=auth(token)
    )


# -- Reading ------------------------------------------------------------------


def test_a_tree_lists_its_pending_suggestions(client, tree_with_suggestion):
    body = _list(client, tree_with_suggestion["tree"]).json()

    assert len(body) == 1
    assert body[0]["name"] == "Ground Transport"
    assert body[0]["state"] == "pending"


def test_a_suggestion_names_where_it_would_go(client, tree_with_suggestion):
    """The reviewer is judging "would be added under X", so the path is resolved
    server-side rather than costing a lookup per suggestion."""
    body = _list(client, tree_with_suggestion["tree"]).json()

    assert body[0]["parent_path"] == "Indirect > Travel & Entertainment"


def test_the_evidence_is_reachable(client, tree_with_suggestion):
    """A proposal a reviewer cannot check is one they cannot responsibly accept,
    and "the model thought so" is not an argument about a chart of accounts."""
    evidence = _list(client, tree_with_suggestion["tree"]).json()[0]["evidence"]

    assert len(evidence) == 1
    assert evidence[0]["item_name"] == "Togbillet"
    assert evidence[0]["vendor_name"] == "DSB"
    assert evidence[0]["level_3"] == "Airfare", "where it landed is half the argument"
    assert evidence[0]["id"] == tree_with_suggestion["line"]


def test_any_member_may_read_them(client, tree_with_suggestion):
    """Like the tree itself: seeing a proposal grants nothing."""
    assert _list(client, tree_with_suggestion["tree"], token="tok_viewerA").status_code == 200


def test_another_organizations_tree_is_404(client, tree_with_suggestion):
    """A tree outside the caller's org is not ours to disclose the existence of."""
    assert _list(client, tree_with_suggestion["tree"], token="tokB").status_code == 404


# -- Accepting ----------------------------------------------------------------


def test_accepting_creates_the_node_under_the_named_parent(
    client, tree_with_suggestion, engine
):
    res = client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/accept",
        headers=auth("tokA"),
    )

    assert res.status_code == 200
    node_id = res.json()["created_category_id"]
    with Session(engine) as s:
        node = s.get(SpendCategory, node_id)
        assert node.name == "Ground Transport"
        assert node.parent_id == tree_with_suggestion["parent"]


def test_the_created_node_carries_a_resolvable_path(client, tree_with_suggestion, engine):
    """The reason acceptance goes through `service.add_node` rather than writing
    the table: only the service keeps `parent_id` and the materialized path in
    step, and a node whose path resolves to nothing is the stale state the
    stored pointer exists to prevent."""
    res = client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/accept",
        headers=auth("tokA"),
    )

    with Session(engine) as s:
        node = s.get(SpendCategory, res.json()["created_category_id"])
        assert (node.level_1, node.level_2, node.level_3) == (
            "Indirect", "Travel & Entertainment", "Ground Transport"
        )
        assert node.depth == 3


def test_accepting_marks_it_accepted_and_records_who(client, tree_with_suggestion, engine):
    client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/accept",
        headers=auth("tokA"),
    )

    with Session(engine) as s:
        row = s.get(SpendCategorySuggestion, tree_with_suggestion["suggestion"])
        assert row.state == SuggestionState.ACCEPTED
        assert row.resolved_by and row.resolved_at


def test_accepting_twice_is_a_conflict(client, tree_with_suggestion):
    path = f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/accept"
    client.post(path, headers=auth("tokA"))

    assert client.post(path, headers=auth("tokA")).status_code == 409


def test_an_orphaned_parent_cannot_be_accepted(client, tree_with_suggestion, engine):
    """The suggestion stays readable — it records a real observation — but there
    is nothing left to hang it under."""
    with Session(engine) as s:
        row = s.get(SpendCategorySuggestion, tree_with_suggestion["suggestion"])
        row.parent_id = None
        s.add(row)
        s.commit()

    res = client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/accept",
        headers=auth("tokA"),
    )

    assert res.status_code == 409
    assert _list(client, tree_with_suggestion["tree"]).json()[0]["acceptable"] is False


# -- Dismissing ---------------------------------------------------------------


def test_dismissing_is_remembered_not_deleted(client, tree_with_suggestion, engine):
    """The suggester reads settled proposals so it does not re-argue a question
    the customer has answered."""
    res = client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/dismiss",
        headers=auth("tokA"),
    )

    assert res.status_code == 200
    with Session(engine) as s:
        row = s.get(SpendCategorySuggestion, tree_with_suggestion["suggestion"])
        assert row is not None and row.state == SuggestionState.DISMISSED


def test_a_dismissed_suggestion_leaves_the_pending_list(client, tree_with_suggestion):
    client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/dismiss",
        headers=auth("tokA"),
    )

    assert _list(client, tree_with_suggestion["tree"]).json() == []
    assert len(_list(client, tree_with_suggestion["tree"], query="?state=dismissed").json()) == 1


def test_an_accepted_suggestion_cannot_then_be_dismissed(client, tree_with_suggestion):
    client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/accept",
        headers=auth("tokA"),
    )

    res = client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/dismiss",
        headers=auth("tokA"),
    )

    assert res.status_code == 409


# -- Who may act --------------------------------------------------------------


@pytest.mark.parametrize("action", ["accept", "dismiss"])
def test_a_viewer_may_not_act(client, tree_with_suggestion, action):
    res = client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/{action}",
        headers=auth("tok_viewerA"),
    )

    assert res.status_code == 403


@pytest.mark.parametrize("action", ["accept", "dismiss"])
def test_another_organization_may_not_act(client, tree_with_suggestion, action):
    """403, not 404 — and that leaks nothing.

    The role gate runs before the row is looked up, so Org B's member is refused
    for the same reason whether the id is real or invented. The `404` rule
    protects the *existence* of another tenant's data, and an answer that does
    not depend on existence cannot disclose it. Asserted alongside a made-up id
    so the indistinguishability is the thing being tested.
    """
    real = client.post(
        f"/api/v1/spend-tree-suggestions/{tree_with_suggestion['suggestion']}/{action}",
        headers=auth("tokB"),
    )
    invented = client.post(
        f"/api/v1/spend-tree-suggestions/does-not-exist/{action}", headers=auth("tokB")
    )

    assert real.status_code == 403
    assert real.status_code == invented.status_code


def test_an_unknown_suggestion_is_404(client, seed):
    assert client.post(
        "/api/v1/spend-tree-suggestions/nope/dismiss", headers=auth("tokA")
    ).status_code == 404
