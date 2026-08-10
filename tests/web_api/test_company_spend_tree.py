"""A company is never left without a taxonomy, and a change of taxonomy costs nothing."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from web_api.db.models import Company, InvoiceLine, Organization, SpendTree
from web_api.db.models.enums import SpendTreeSource
from web_api.spend_trees import service


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create(client, name="New Co", **extra):
    body = {
        "name": name,
        "base_currency": "DKK",
        "integration": {"erp_type": "mock", "credentials": {}},
        **extra,
    }
    return client.post("/api/v1/companies", json=body, headers=_auth("tokA"))


def test_a_created_company_gets_the_organizations_default_tree(client, engine, seed):
    response = _create(client)
    assert response.status_code == 201
    body = response.json()
    assert body["spend_tree_id"] is not None
    assert body["spend_tree_name"] == "Default spend tree"

    with Session(engine) as s:
        tree = s.get(SpendTree, body["spend_tree_id"])
        assert tree.source == SpendTreeSource.DEFAULT_TEMPLATE
        assert tree.organization_id == seed["org_a"]
        assert len(service.tree_nodes(s, tree.id)) > 0, "the template must be seeded"


def test_a_second_company_reuses_the_same_copy(client, engine, seed):
    first = _create(client, "First").json()
    second = _create(client, "Second").json()

    assert first["spend_tree_id"] == second["spend_tree_id"]
    with Session(engine) as s:
        trees = s.exec(
            select(SpendTree).where(
                SpendTree.organization_id == seed["org_a"],
                SpendTree.source == SpendTreeSource.DEFAULT_TEMPLATE,
            )
        ).all()
        assert len(trees) == 1, "an organization holds one template copy, not one per company"


def test_a_named_tree_is_used_as_given(client, engine, seed):
    with Session(engine) as s:
        custom = service.create_tree(s, seed["org_a"], "Custom", max_depth=4)
        s.commit()
        custom_id = custom.id

    body = _create(client, spend_tree_id=custom_id).json()
    assert body["spend_tree_id"] == custom_id
    assert body["spend_tree_name"] == "Custom"


def test_a_tree_from_another_organization_creates_nothing(client, engine, seed):
    with Session(engine) as s:
        theirs = service.create_tree(s, seed["org_b"], "Org B tree")
        s.commit()
        theirs_id = theirs.id

    before = len(client.get("/api/v1/companies", headers=_auth("tokA")).json())
    response = _create(client, spend_tree_id=theirs_id)

    assert response.status_code == 422
    after = client.get("/api/v1/companies", headers=_auth("tokA")).json()
    assert len(after) == before, "no company may survive a rejected tree"


def test_the_company_listing_carries_its_tree(client, engine, seed):
    _create(client, "Listed")
    rows = client.get("/api/v1/companies", headers=_auth("tokA")).json()
    listed = next(r for r in rows if r["name"] == "Listed")
    assert listed["spend_tree_name"] == "Default spend tree"


# -- Reassignment ------------------------------------------------------------


@pytest.fixture()
def assigned(engine, seed):
    """Org A's company on a tree, with its categorized line pointing into it."""
    with Session(engine) as s:
        old = service.create_tree(s, seed["org_a"], "Old", max_depth=3)
        l1 = service.add_node(s, old, "Indirect")
        l2 = service.add_node(s, old, "Technology", parent_id=l1.id)
        leaf = service.add_node(s, old, "Cloud", parent_id=l2.id)
        company = s.get(Company, seed["comp_a"])
        company.spend_tree_id = old.id
        line = s.get(InvoiceLine, seed["line_a2"])
        line.level_1, line.level_2, line.level_3 = "Indirect", "Technology", "Cloud"
        line.status = "verified"
        line.spend_category_id = leaf.id
        s.add(company)
        s.add(line)
        s.commit()
        return {"old": old.id, "leaf": leaf.id}


def _new_tree(engine, org_id, leaf_name):
    with Session(engine) as s:
        tree = service.create_tree(s, org_id, f"New ({leaf_name})", max_depth=3)
        l1 = service.add_node(s, tree, "Indirect")
        l2 = service.add_node(s, tree, "Technology", parent_id=l1.id)
        leaf = service.add_node(s, tree, leaf_name, parent_id=l2.id)
        s.commit()
        return tree.id, leaf.id


def test_reassignment_reports_what_it_cost(client, engine, seed, assigned):
    new_id, _ = _new_tree(engine, seed["org_a"], "Hosting")

    response = client.patch(
        f"/api/v1/companies/{seed['comp_a']}",
        json={"spend_tree_id": new_id}, headers=_auth("tokA"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["spend_tree_id"] == new_id
    assert body["stale_lines"] == 1, "the caller must learn the consequence here"

    with Session(engine) as s:
        line = s.get(InvoiceLine, seed["line_a2"])
        assert line.spend_category_id is None
        assert line.status == "verified", "no verification is discarded"
        assert line.level_3 == "Cloud", "the decision stays on record"


def test_an_identical_path_re_resolves_and_costs_nothing(client, engine, seed, assigned):
    new_id, new_leaf = _new_tree(engine, seed["org_a"], "Cloud")

    response = client.patch(
        f"/api/v1/companies/{seed['comp_a']}",
        json={"spend_tree_id": new_id}, headers=_auth("tokA"),
    )
    assert response.json()["stale_lines"] == 0

    with Session(engine) as s:
        assert s.get(InvoiceLine, seed["line_a2"]).spend_category_id == new_leaf


def test_reassigning_to_another_organizations_tree_is_rejected(client, engine, seed, assigned):
    theirs, _ = _new_tree(engine, seed["org_b"], "Cloud")

    response = client.patch(
        f"/api/v1/companies/{seed['comp_a']}",
        json={"spend_tree_id": theirs}, headers=_auth("tokA"),
    )
    assert response.status_code == 422
    with Session(engine) as s:
        assert s.get(Company, seed["comp_a"]).spend_tree_id == assigned["old"]


def test_a_member_cannot_reassign(client, seed, assigned):
    response = client.patch(
        f"/api/v1/companies/{seed['comp_a']}",
        json={"spend_tree_id": assigned["old"]}, headers=_auth("tok_memberA"),
    )
    assert response.status_code == 403


def test_an_unrelated_patch_leaves_the_tree_alone(client, engine, seed, assigned):
    response = client.patch(
        f"/api/v1/companies/{seed['comp_a']}",
        json={"name": "Renamed"}, headers=_auth("tokA"),
    )
    assert response.status_code == 200
    assert response.json()["stale_lines"] == 0
    with Session(engine) as s:
        line = s.get(InvoiceLine, seed["line_a2"])
        assert line.spend_category_id == assigned["leaf"]
