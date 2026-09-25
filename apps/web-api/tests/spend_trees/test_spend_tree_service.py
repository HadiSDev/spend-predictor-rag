"""The spend-tree service keeps parentage and materialized paths in agreement."""
from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from web_api.db.models import Company, InvoiceLine, Invoice, Organization, SpendCategory, SpendTree
from web_api.db.models.enums import SpendTreeSource
from web_api.spend_trees import service
from web_api.spend_trees.template import DEFAULT_TEMPLATE, TEMPLATE_VERSION


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Organization(id="org", name="Org"))
        s.commit()
        yield s


def _walked_path(s: Session, node: SpendCategory) -> tuple[str, ...]:
    """The path obtained by walking `parent_id` — the thing the stored path must equal."""
    names: list[str] = []
    cursor: SpendCategory | None = node
    while cursor is not None:
        names.append(cursor.name)
        cursor = s.get(SpendCategory, cursor.parent_id) if cursor.parent_id else None
    return tuple(reversed(names))


def _assert_paths_agree(s: Session, tree_id: str) -> None:
    for node in service.tree_nodes(s, tree_id):
        walked = _walked_path(s, node)
        assert service.node_path(node) == walked, (
            f"materialized path {service.node_path(node)} != walked path {walked} "
            f"for node {node.name!r}"
        )
        assert node.depth == len(walked), f"depth {node.depth} != {len(walked)} for {node.name!r}"


def _tree(s: Session, max_depth: int = 4) -> SpendTree:
    tree = service.create_tree(s, "org", "Custom", max_depth=max_depth)
    s.commit()
    return tree


def test_ensure_default_tree_seeds_the_template(session):
    tree = service.ensure_default_tree(session, "org")
    session.commit()

    assert tree.source == SpendTreeSource.DEFAULT_TEMPLATE
    assert tree.max_depth == 3
    assert tree.template_version == TEMPLATE_VERSION

    nodes = service.tree_nodes(session, tree.id)
    assert len(nodes) == len(DEFAULT_TEMPLATE)
    _assert_paths_agree(session, tree.id)

    roots = [n for n in nodes if n.depth == 1]
    assert sorted(n.name for n in roots) == ["Direct", "Indirect"]
    assert all(n.level_2 is None for n in roots)
    assert max(n.depth for n in nodes) == 3


def test_ensure_default_tree_is_idempotent(session):
    first = service.ensure_default_tree(session, "org")
    session.commit()
    second = service.ensure_default_tree(session, "org")
    session.commit()

    assert first.id == second.id
    trees = session.exec(select(SpendTree)).all()
    assert len(trees) == 1, "an organization holds at most one template copy"


def test_a_template_copy_is_tenant_local(session):
    session.add(Organization(id="org2", name="Other"))
    session.commit()
    a = service.ensure_default_tree(session, "org")
    b = service.ensure_default_tree(session, "org2")
    session.commit()

    node = next(n for n in service.tree_nodes(session, a.id) if n.name == "Technology")
    service.rename_node(session, node, "Tech")
    session.commit()

    other_names = {n.name for n in service.tree_nodes(session, b.id)}
    assert "Technology" in other_names and "Tech" not in other_names


def test_add_node_materializes_the_path(session):
    tree = _tree(session)
    l1 = service.add_node(session, tree, "Indirect")
    l2 = service.add_node(session, tree, "Technology", parent_id=l1.id)
    l3 = service.add_node(session, tree, "Cloud Infrastructure", parent_id=l2.id)
    leaf = service.add_node(session, tree, "Compute", parent_id=l3.id)
    session.commit()

    assert leaf.depth == 4
    assert (leaf.level_1, leaf.level_2, leaf.level_3, leaf.level_4) == (
        "Indirect", "Technology", "Cloud Infrastructure", "Compute"
    )
    _assert_paths_agree(session, tree.id)


def test_rename_rewrites_descendant_paths(session):
    tree = _tree(session)
    l1 = service.add_node(session, tree, "Indirect")
    l2 = service.add_node(session, tree, "Technology", parent_id=l1.id)
    leaf = service.add_node(session, tree, "Cloud", parent_id=l2.id)
    session.commit()

    service.rename_node(session, l2, "IT")
    session.commit()
    session.refresh(leaf)

    assert leaf.level_2 == "IT", "a descendant kept a path naming an ancestor that is gone"
    _assert_paths_agree(session, tree.id)


def test_move_rewrites_paths_and_clears_the_tail(session):
    tree = _tree(session)
    a = service.add_node(session, tree, "Indirect")
    b = service.add_node(session, tree, "Direct")
    mid = service.add_node(session, tree, "Technology", parent_id=a.id)
    leaf = service.add_node(session, tree, "Cloud", parent_id=mid.id)
    session.commit()

    service.move_node(session, mid, b.id)
    session.commit()
    session.refresh(leaf)

    assert leaf.level_1 == "Direct" and leaf.level_3 == "Cloud"
    _assert_paths_agree(session, tree.id)

    service.move_node(session, mid, None)
    session.commit()
    session.refresh(leaf)
    assert (leaf.level_1, leaf.level_2, leaf.level_3) == ("Technology", "Cloud", None)
    _assert_paths_agree(session, tree.id)


def test_a_node_cannot_be_moved_beneath_itself(session):
    tree = _tree(session)
    root = service.add_node(session, tree, "Indirect")
    child = service.add_node(session, tree, "Technology", parent_id=root.id)
    session.commit()

    with pytest.raises(service.SpendTreeError):
        service.move_node(session, root, child.id)


def test_depth_beyond_max_is_rejected(session):
    tree = _tree(session, max_depth=3)
    l1 = service.add_node(session, tree, "Indirect")
    l2 = service.add_node(session, tree, "Technology", parent_id=l1.id)
    l3 = service.add_node(session, tree, "Cloud", parent_id=l2.id)
    session.commit()

    with pytest.raises(service.SpendTreeError) as excinfo:
        service.add_node(session, tree, "Compute", parent_id=l3.id)
    assert "3 levels" in str(excinfo.value)


def test_a_move_that_would_push_children_too_deep_is_rejected(session):
    tree = _tree(session, max_depth=3)
    a = service.add_node(session, tree, "Indirect")
    b = service.add_node(session, tree, "Direct")
    mid = service.add_node(session, tree, "Technology", parent_id=b.id)
    service.add_node(session, tree, "Cloud", parent_id=mid.id)
    session.commit()

    child_of_a = service.add_node(session, tree, "Services", parent_id=a.id)
    session.commit()
    with pytest.raises(service.SpendTreeError):
        service.move_node(session, mid, child_of_a.id)


def test_lowering_max_depth_with_deep_nodes_is_rejected(session):
    tree = _tree(session, max_depth=4)
    l1 = service.add_node(session, tree, "Indirect")
    l2 = service.add_node(session, tree, "Technology", parent_id=l1.id)
    l3 = service.add_node(session, tree, "Cloud", parent_id=l2.id)
    service.add_node(session, tree, "Compute", parent_id=l3.id)
    session.commit()

    with pytest.raises(service.SpendTreeError):
        service.update_tree(session, tree, max_depth=3)


def test_raising_max_depth_is_allowed(session):
    tree = _tree(session, max_depth=3)
    service.update_tree(session, tree, max_depth=4)
    session.commit()
    assert tree.max_depth == 4


def test_the_default_copy_cannot_be_deepened_in_place(session):
    tree = service.ensure_default_tree(session, "org")
    session.commit()
    with pytest.raises(service.SpendTreeError):
        service.update_tree(session, tree, max_depth=4)


def test_duplicate_sibling_is_rejected(session):
    tree = _tree(session)
    root = service.add_node(session, tree, "Indirect")
    service.add_node(session, tree, "Technology", parent_id=root.id)
    session.commit()

    with pytest.raises(service.SpendTreeError) as excinfo:
        service.add_node(session, tree, "Technology", parent_id=root.id)
    assert excinfo.value.code == "conflict"


def test_the_same_name_under_a_different_parent_is_allowed(session):
    tree = _tree(session)
    a = service.add_node(session, tree, "Indirect")
    b = service.add_node(session, tree, "Direct")
    service.add_node(session, tree, "Services", parent_id=a.id)
    service.add_node(session, tree, "Services", parent_id=b.id)
    session.commit()
    assert len(service.tree_nodes(session, tree.id)) == 4


def test_duplicate_code_within_a_tree_is_rejected(session):
    tree = _tree(session)
    root = service.add_node(session, tree, "Indirect")
    service.add_node(session, tree, "Technology", parent_id=root.id, code="6010")
    session.commit()

    with pytest.raises(service.SpendTreeError):
        service.add_node(session, tree, "Logistics", parent_id=root.id, code="6010")


def test_clone_is_independent_of_its_source(session):
    source = service.ensure_default_tree(session, "org")
    session.commit()

    clone = service.clone_tree(session, source, "Our tree")
    session.commit()

    assert clone.source == SpendTreeSource.CUSTOM, (
        "a clone of the template is the customer's own tree from the moment it exists"
    )
    assert len(service.tree_nodes(session, clone.id)) == len(service.tree_nodes(session, source.id))
    _assert_paths_agree(session, clone.id)

    node = next(n for n in service.tree_nodes(session, clone.id) if n.name == "Technology")
    service.rename_node(session, node, "IT")
    session.commit()

    source_names = {n.name for n in service.tree_nodes(session, source.id)}
    assert "Technology" in source_names and "IT" not in source_names


def test_clone_can_declare_a_deeper_maximum(session):
    source = service.ensure_default_tree(session, "org")
    session.commit()
    clone = service.clone_tree(session, source, "Deep", max_depth=4)
    session.commit()
    assert clone.max_depth == 4

    leaf = next(n for n in service.tree_nodes(session, clone.id) if n.name == "Cloud Infrastructure")
    child = service.add_node(session, clone, "Compute", parent_id=leaf.id)
    session.commit()
    assert child.depth == 4 and child.level_4 == "Compute"


def test_deleting_a_node_with_children_is_refused(session):
    tree = _tree(session)
    root = service.add_node(session, tree, "Indirect")
    service.add_node(session, tree, "Technology", parent_id=root.id)
    session.commit()

    with pytest.raises(service.SpendTreeError) as excinfo:
        service.delete_node(session, root)
    assert excinfo.value.code == "conflict"


def test_deleting_a_referenced_node_keeps_the_line_and_its_levels(session):
    tree = _tree(session)
    root = service.add_node(session, tree, "Indirect")
    leaf = service.add_node(session, tree, "Technology", parent_id=root.id)
    session.add(Company(id="co", organization_id="org", name="Co", spend_tree_id=tree.id))
    session.add(Invoice(id="inv", company_id="co", status="categorized"))
    session.add(InvoiceLine(
        id="ln", company_id="co", invoice_id="inv", status="verified",
        level_1="Indirect", level_2="Technology", spend_category_id=leaf.id,
    ))
    session.commit()

    affected = service.delete_node(session, leaf)
    session.commit()

    assert affected == 1
    line = session.get(InvoiceLine, "ln")
    assert line.spend_category_id is None
    assert (line.level_1, line.level_2) == ("Indirect", "Technology"), (
        "the record of what was decided must survive the node it pointed at"
    )
    assert line.status == "verified"


def test_an_assigned_tree_cannot_be_archived(session):
    tree = _tree(session)
    session.add(Company(id="co", organization_id="org", name="Acme", spend_tree_id=tree.id))
    session.commit()

    with pytest.raises(service.SpendTreeError) as excinfo:
        service.archive_tree(session, tree)
    assert excinfo.value.code == "conflict"
    assert "Acme" in str(excinfo.value), "the refusal must name what is blocking it"


def test_an_unassigned_tree_archives(session):
    tree = _tree(session)
    service.archive_tree(session, tree)
    session.commit()
    assert tree.archived_at is not None


def test_a_tree_in_another_organization_is_not_found(session):
    tree = _tree(session)
    session.add(Organization(id="org2", name="Other"))
    session.commit()

    with pytest.raises(service.SpendTreeError) as excinfo:
        service.get_tree(session, tree.id, "org2")
    assert excinfo.value.code == "not_found"
