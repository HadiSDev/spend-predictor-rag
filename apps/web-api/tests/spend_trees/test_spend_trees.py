"""The spend-tree API: reads for everyone, writes for managers, 404 across tenants."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from web_api.db.models import Company, InvoiceLine, SpendCategory, SpendTree
from web_api.spend_trees import service

CSV = """level_1,level_2,level_3,description,code
Indirect,Technology,Cloud,Hosting,6010
Indirect,Technology,Software,Licences,6020
"""


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def tree(engine, seed):
    """A three-level tree in Org A, assigned to nothing."""
    with Session(engine) as s:
        t = service.ensure_default_tree(s, seed["org_a"])
        s.commit()
        return t.id


def test_a_member_can_read_the_trees(client, seed, tree):
    listed = client.get("/api/v1/spend-trees", headers=_auth("tok_memberA"))
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["source"] == "default_template"
    assert body[0]["max_depth"] == 3
    assert body[0]["node_count"] > 0
    assert body[0]["company_ids"] == []


def test_detail_returns_a_renderable_hierarchy(client, tree):
    response = client.get(f"/api/v1/spend-trees/{tree}", headers=_auth("tok_viewerA"))
    assert response.status_code == 200
    nodes = response.json()["nodes"]

    ids = {n["id"] for n in nodes}
    assert all(n["parent_id"] in ids for n in nodes if n["parent_id"])
    assert [n["depth"] for n in nodes] == sorted(n["depth"] for n in nodes)

    root = next(n for n in nodes if n["name"] == "Indirect")
    assert root["depth"] == 1 and root["level_1"] == "Indirect" and root["level_2"] is None


def test_another_organizations_tree_is_not_found(client, tree):
    assert client.get(f"/api/v1/spend-trees/{tree}", headers=_auth("tokB")).status_code == 404


def test_archived_trees_are_hidden_unless_asked_for(client, engine, seed, tree):
    client.post(f"/api/v1/spend-trees/{tree}/archive", headers=_auth("tokA"))
    assert client.get("/api/v1/spend-trees", headers=_auth("tokA")).json() == []
    shown = client.get(
        "/api/v1/spend-trees?include_archived=true", headers=_auth("tokA")
    ).json()
    assert len(shown) == 1 and shown[0]["archived_at"] is not None


def test_clone_produces_an_independent_tree(client, tree):
    source = client.get(f"/api/v1/spend-trees/{tree}", headers=_auth("tokA")).json()
    created = client.post(
        "/api/v1/spend-trees",
        json={"name": "Our tree", "max_depth": 4, "source_tree_id": tree},
        headers=_auth("tokA"),
    )
    assert created.status_code == 201
    clone = created.json()
    assert clone["source"] == "custom"
    assert clone["max_depth"] == 4
    assert len(clone["nodes"]) == len(source["nodes"])
    assert {n["id"] for n in clone["nodes"]}.isdisjoint({n["id"] for n in source["nodes"]})


def test_an_empty_tree_can_be_built_from_scratch(client):
    created = client.post(
        "/api/v1/spend-trees", json={"name": "From scratch"}, headers=_auth("tokA")
    )
    assert created.status_code == 201
    assert created.json()["nodes"] == []
    assert created.json()["max_depth"] == 3


def test_cloning_another_organizations_tree_is_not_found(client, engine, seed, tree):
    with Session(engine) as s:
        theirs = service.create_tree(s, seed["org_b"], "Org B tree")
        s.commit()
        theirs_id = theirs.id

    response = client.post(
        "/api/v1/spend-trees",
        json={"name": "Theirs", "source_tree_id": theirs_id},
        headers=_auth("tokA"),
    )
    assert response.status_code == 404


def test_a_member_cannot_create(client):
    response = client.post(
        "/api/v1/spend-trees", json={"name": "Nope"}, headers=_auth("tok_memberA")
    )
    assert response.status_code == 403


def _node_named(client, tree, name):
    nodes = client.get(f"/api/v1/spend-trees/{tree}", headers=_auth("tokA")).json()["nodes"]
    return next(n for n in nodes if n["name"] == name)


def test_adding_a_child_materializes_its_path(client, tree):
    parent = _node_named(client, tree, "Technology")
    created = client.post(
        f"/api/v1/spend-trees/{tree}/nodes",
        json={"name": "Observability", "parent_id": parent["id"], "code": "6011"},
        headers=_auth("tokA"),
    )
    assert created.status_code == 201
    node = created.json()
    assert node["depth"] == 3
    assert [node["level_1"], node["level_2"], node["level_3"]] == [
        "Indirect", "Technology", "Observability"
    ]


def test_a_fourth_level_is_refused_on_a_three_level_tree(client, tree):
    leaf = _node_named(client, tree, "Cloud Infrastructure")
    response = client.post(
        f"/api/v1/spend-trees/{tree}/nodes",
        json={"name": "Compute", "parent_id": leaf["id"]},
        headers=_auth("tokA"),
    )
    assert response.status_code == 422
    assert "3 levels" in response.json()["detail"]


def test_a_duplicate_sibling_is_a_conflict(client, tree):
    parent = _node_named(client, tree, "Technology")
    response = client.post(
        f"/api/v1/spend-trees/{tree}/nodes",
        json={"name": "Software", "parent_id": parent["id"]},
        headers=_auth("tokA"),
    )
    assert response.status_code == 409


def test_renaming_rewrites_descendant_paths(client, tree):
    node = _node_named(client, tree, "Technology")
    response = client.patch(
        f"/api/v1/spend-tree-nodes/{node['id']}", json={"name": "IT"}, headers=_auth("tokA")
    )
    assert response.status_code == 200
    leaf = _node_named(client, tree, "Cloud Infrastructure")
    assert leaf["level_2"] == "IT"


def test_deleting_a_node_with_children_is_a_conflict(client, tree):
    node = _node_named(client, tree, "Technology")
    response = client.delete(f"/api/v1/spend-tree-nodes/{node['id']}", headers=_auth("tokA"))
    assert response.status_code == 409
    assert "child categories" in response.json()["detail"]


def test_deleting_a_referenced_leaf_reports_the_lines_it_orphans(client, engine, seed, tree):
    leaf = _node_named(client, tree, "Cloud Infrastructure")
    with Session(engine) as s:
        line = s.get(InvoiceLine, seed["line_a2"])
        line.spend_category_id = leaf["id"]
        s.add(line)
        s.commit()

    response = client.delete(f"/api/v1/spend-tree-nodes/{leaf['id']}", headers=_auth("tokA"))
    assert response.status_code == 200
    assert response.json()["stale_lines"] == 1

    with Session(engine) as s:
        line = s.get(InvoiceLine, seed["line_a2"])
        assert line.spend_category_id is None
        assert line.level_2 == "Technology", "the decision survives the node"


def test_a_viewer_cannot_edit_a_node(client, tree):
    node = _node_named(client, tree, "Technology")
    response = client.patch(
        f"/api/v1/spend-tree-nodes/{node['id']}", json={"name": "IT"},
        headers=_auth("tok_viewerA"),
    )
    assert response.status_code == 403


def test_a_tree_in_use_cannot_be_archived(client, engine, seed, tree):
    with Session(engine) as s:
        company = s.get(Company, seed["comp_a"])
        company.spend_tree_id = tree
        s.add(company)
        s.commit()

    response = client.post(f"/api/v1/spend-trees/{tree}/archive", headers=_auth("tokA"))
    assert response.status_code == 409
    assert "Acme A" in response.json()["detail"], "the refusal must name what blocks it"


def test_import_loads_a_csv(client, engine, seed):
    created = client.post(
        "/api/v1/spend-trees", json={"name": "Imported"}, headers=_auth("tokA")
    ).json()
    response = client.post(
        f"/api/v1/spend-trees/{created['id']}/import",
        json={"content": CSV},
        headers=_auth("tokA"),
    )
    assert response.status_code == 200
    assert response.json()["created"] == 4

    detail = client.get(f"/api/v1/spend-trees/{created['id']}", headers=_auth("tokA")).json()
    assert {n["name"] for n in detail["nodes"]} == {
        "Indirect", "Technology", "Cloud", "Software"
    }


def test_a_bad_row_rejects_the_file_and_names_the_line(client):
    created = client.post(
        "/api/v1/spend-trees", json={"name": "Imported"}, headers=_auth("tokA")
    ).json()
    broken = CSV + "Indirect,,Orphan,No parent,9999\n"

    response = client.post(
        f"/api/v1/spend-trees/{created['id']}/import",
        json={"content": broken},
        headers=_auth("tokA"),
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["errors"][0]["line"] == 4

    after = client.get(f"/api/v1/spend-trees/{created['id']}", headers=_auth("tokA")).json()
    assert after["nodes"] == [], "a rejected import must write nothing"


def test_replace_asks_before_orphaning_lines(client, engine, seed):
    created = client.post(
        "/api/v1/spend-trees", json={"name": "Imported"}, headers=_auth("tokA")
    ).json()
    client.post(
        f"/api/v1/spend-trees/{created['id']}/import",
        json={"content": CSV}, headers=_auth("tokA"),
    )
    detail = client.get(f"/api/v1/spend-trees/{created['id']}", headers=_auth("tokA")).json()
    doomed = next(n for n in detail["nodes"] if n["name"] == "Software")
    with Session(engine) as s:
        line = s.get(InvoiceLine, seed["line_a2"])
        line.spend_category_id = doomed["id"]
        s.add(line)
        s.commit()

    smaller = "level_1,level_2,level_3\nIndirect,Technology,Cloud\n"
    blocked = client.post(
        f"/api/v1/spend-trees/{created['id']}/import?mode=replace",
        json={"content": smaller}, headers=_auth("tokA"),
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["affected_lines"] == 1

    confirmed = client.post(
        f"/api/v1/spend-trees/{created['id']}/import?mode=replace&confirm=true",
        json={"content": smaller}, headers=_auth("tokA"),
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["stale_lines"] == 1


def test_import_requires_management(client, tree):
    response = client.post(
        f"/api/v1/spend-trees/{tree}/import",
        json={"content": CSV}, headers=_auth("tok_memberA"),
    )
    assert response.status_code == 403


def test_the_default_tree_can_be_materialized_on_demand(client, engine, seed):
    assert client.get("/api/v1/spend-trees", headers=_auth("tokA")).json() == []

    created = client.post("/api/v1/spend-trees/default", headers=_auth("tokA"))
    assert created.status_code == 200
    body = created.json()
    assert body["source"] == "default_template"
    assert body["max_depth"] == 3
    assert len(body["nodes"]) > 0
    assert {n["name"] for n in body["nodes"] if n["depth"] == 1} == {"Direct", "Indirect"}


def test_materializing_the_default_twice_returns_the_same_tree(client, seed):
    first = client.post("/api/v1/spend-trees/default", headers=_auth("tokA")).json()
    second = client.post("/api/v1/spend-trees/default", headers=_auth("tokA")).json()

    assert first["id"] == second["id"]
    listed = client.get("/api/v1/spend-trees", headers=_auth("tokA")).json()
    assert len([t for t in listed if t["source"] == "default_template"]) == 1


def test_the_default_is_not_confused_with_a_tree_named_default(client, engine, seed):
    response = client.post("/api/v1/spend-trees/default", headers=_auth("tokA"))
    assert response.status_code == 200, "the literal path must win over /spend-trees"


def test_a_member_cannot_materialize_the_default(client, seed):
    response = client.post("/api/v1/spend-trees/default", headers=_auth("tok_memberA"))
    assert response.status_code == 403


def test_an_unused_tree_is_deleted_outright(client, engine, seed, tree):
    response = client.delete(f"/api/v1/spend-trees/{tree}", headers=_auth("tokA"))
    assert response.status_code == 200
    assert response.json()["stale_lines"] == 0

    assert client.get("/api/v1/spend-trees", headers=_auth("tokA")).json() == []
    with Session(engine) as s:
        assert s.get(SpendTree, tree) is None
        assert s.exec(
            select(SpendCategory).where(SpendCategory.spend_tree_id == tree)
        ).all() == [], "its nodes go with it"


def test_a_tree_in_use_cannot_be_deleted(client, engine, seed, tree):
    with Session(engine) as s:
        company = s.get(Company, seed["comp_a"])
        company.spend_tree_id = tree
        s.add(company)
        s.commit()

    response = client.delete(f"/api/v1/spend-trees/{tree}", headers=_auth("tokA"))
    assert response.status_code == 409
    assert "Acme A" in response.json()["detail"]
    with Session(engine) as s:
        assert s.get(SpendTree, tree) is not None


def test_deleting_a_tree_categorized_lines_use_needs_confirming(client, engine, seed, tree):
    leaf = _node_named(client, tree, "Cloud Infrastructure")
    with Session(engine) as s:
        line = s.get(InvoiceLine, seed["line_a2"])
        line.spend_category_id = leaf["id"]
        s.add(line)
        s.commit()

    blocked = client.delete(f"/api/v1/spend-trees/{tree}", headers=_auth("tokA"))
    assert blocked.status_code == 409
    assert "1 invoice line" in blocked.json()["detail"]
    with Session(engine) as s:
        assert s.get(SpendTree, tree) is not None, "a refusal deletes nothing"

    confirmed = client.delete(
        f"/api/v1/spend-trees/{tree}?confirm=true", headers=_auth("tokA")
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["stale_lines"] == 1

    with Session(engine) as s:
        line = s.get(InvoiceLine, seed["line_a2"])
        assert line.spend_category_id is None
        assert line.level_2 == "Technology", "the decision survives the tree"
        assert line.status == "ai_categorized"


def test_a_member_cannot_delete_a_tree(client, tree):
    response = client.delete(f"/api/v1/spend-trees/{tree}", headers=_auth("tok_memberA"))
    assert response.status_code == 403


def test_another_organizations_tree_cannot_be_deleted(client, engine, seed):
    with Session(engine) as s:
        theirs = service.create_tree(s, seed["org_b"], "Org B tree")
        s.commit()
        theirs_id = theirs.id

    response = client.delete(f"/api/v1/spend-trees/{theirs_id}", headers=_auth("tokA"))
    assert response.status_code == 404
    with Session(engine) as s:
        assert s.get(SpendTree, theirs_id) is not None
