"""Verifying a line by naming its spend-tree node."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from web_api.db.models import AuditLog, Company, InvoiceLine
from web_api.spend_trees import service


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def deep_tree(engine, seed):
    """A four-level tree assigned to Org A's company."""
    with Session(engine) as s:
        tree = service.create_tree(s, seed["org_a"], "Deep", max_depth=4)
        l1 = service.add_node(s, tree, "Indirect")
        l2 = service.add_node(s, tree, "Technology", parent_id=l1.id)
        l3 = service.add_node(s, tree, "Cloud", parent_id=l2.id)
        leaf = service.add_node(s, tree, "Compute", parent_id=l3.id)
        company = s.get(Company, seed["comp_a"])
        company.spend_tree_id = tree.id
        s.add(company)
        s.commit()
        return {"tree": tree.id, "leaf": leaf.id, "mid": l2.id}


def test_choosing_a_node_sets_the_whole_path(client, engine, seed, deep_tree):
    response = client.post(
        f"/api/v1/invoice-lines/{seed['line_a1']}/verify",
        json={"spend_category_id": deep_tree["leaf"]},
        headers=_auth("tokA"),
    )
    assert response.status_code == 200
    body = response.json()
    assert [body["level_1"], body["level_2"], body["level_3"], body["level_4"]] == [
        "Indirect", "Technology", "Cloud", "Compute"
    ]
    assert body["status"] == "verified"
    assert body["category_stale"] is False


def test_the_node_beats_levels_sent_alongside_it(client, seed, deep_tree):
    response = client.post(
        f"/api/v1/invoice-lines/{seed['line_a1']}/verify",
        json={"spend_category_id": deep_tree["leaf"], "level_2": "Nonsense"},
        headers=_auth("tokA"),
    )
    assert response.status_code == 200
    assert response.json()["level_2"] == "Technology", "the node is the authority"


def test_a_non_leaf_node_is_a_legitimate_answer(client, seed, deep_tree):
    response = client.post(
        f"/api/v1/invoice-lines/{seed['line_a1']}/verify",
        json={"spend_category_id": deep_tree["mid"]},
        headers=_auth("tokA"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["level_2"] == "Technology" and body["level_3"] is None


def test_an_unknown_node_is_rejected(client, engine, seed, deep_tree):
    response = client.post(
        f"/api/v1/invoice-lines/{seed['line_a1']}/verify",
        json={"spend_category_id": "no-such-node"}, headers=_auth("tokA"),
    )
    assert response.status_code == 422
    with Session(engine) as s:
        assert s.get(InvoiceLine, seed["line_a1"]).status == "uncategorized"


def test_a_node_from_another_tree_is_rejected(client, engine, seed, deep_tree):
    with Session(engine) as s:
        other = service.create_tree(s, seed["org_a"], "Other", max_depth=3)
        foreign = service.add_node(s, other, "Indirect")
        s.commit()
        foreign_id = foreign.id

    response = client.post(
        f"/api/v1/invoice-lines/{seed['line_a1']}/verify",
        json={"spend_category_id": foreign_id}, headers=_auth("tokA"),
    )
    assert response.status_code == 422
    with Session(engine) as s:
        assert s.get(InvoiceLine, seed["line_a1"]).spend_category_id is None


def test_level_4_is_audited(client, engine, seed, deep_tree):
    client.post(
        f"/api/v1/invoice-lines/{seed['line_a1']}/verify",
        json={"spend_category_id": deep_tree["leaf"]}, headers=_auth("tokA"),
    )
    with Session(engine) as s:
        entry = s.exec(
            select(AuditLog).where(AuditLog.entity_id == seed["line_a1"])
        ).one()
    fields = {c["field"]: c["new"] for c in entry.changes}
    assert entry.action == "edit"
    assert fields["level_4"] == "Compute"


def test_a_line_with_a_decision_and_no_node_reads_stale(client, seed):
    body = client.get(
        f"/api/v1/invoice-lines?company_id={seed['comp_a']}", headers=_auth("tokA")
    ).json()
    by_id = {row["id"]: row for row in body["items"]}
    assert by_id[seed["line_a2"]]["category_stale"] is True
    assert by_id[seed["line_a1"]]["category_stale"] is False, (
        "an uncategorized line has no decision to go stale"
    )


def test_the_stale_filter_returns_exactly_that_set(client, seed):
    stale = client.get(
        f"/api/v1/invoice-lines?company_id={seed['comp_a']}&stale=true",
        headers=_auth("tokA"),
    ).json()
    assert [row["id"] for row in stale["items"]] == [seed["line_a2"]]

    fresh = client.get(
        f"/api/v1/invoice-lines?company_id={seed['comp_a']}&stale=false",
        headers=_auth("tokA"),
    ).json()
    assert [row["id"] for row in fresh["items"]] == [seed["line_a1"]]


def test_re_verifying_a_stale_line_clears_the_flag(client, seed, deep_tree):
    response = client.post(
        f"/api/v1/invoice-lines/{seed['line_a2']}/verify",
        json={"spend_category_id": deep_tree["leaf"]}, headers=_auth("tokA"),
    )
    assert response.json()["category_stale"] is False

    remaining = client.get(
        f"/api/v1/invoice-lines?company_id={seed['comp_a']}&stale=true",
        headers=_auth("tokA"),
    ).json()
    assert remaining["items"] == []


def test_stale_is_scoped_like_every_other_filter(client, seed):
    body = client.get("/api/v1/invoice-lines?stale=true", headers=_auth("tokB")).json()
    assert all(row["id"] != seed["line_a2"] for row in body["items"])
