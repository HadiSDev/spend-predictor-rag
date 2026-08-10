"""The sync categorizes against the company's own tree, or not at all.

Two companies in one organization may be on different taxonomies, and a company
on none must produce an honest backlog rather than categories nobody chose.
"""
from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from web_api.db.models import (
    Company,
    Invoice,
    InvoiceLine,
    Organization,
    SpendCategory,
)
from web_api.spend_trees import service
from ai_api.sync.categorizer import (
    build_candidates_from_tree,
    categorize,
    default_candidates,
)
from ai_api.sync.runner import _categorize_pending, _tree_candidates


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


def _nodes(s: Session, tree_id: str):
    return s.exec(select(SpendCategory).where(SpendCategory.spend_tree_id == tree_id)).all()


# -- Candidate construction --------------------------------------------------


def test_candidates_are_leaves_only(session):
    """An interior node is a heading; matching to it throws away the tree's precision."""
    tree = service.ensure_default_tree(session, "org")
    session.commit()

    candidates = build_candidates_from_tree(_nodes(session, tree.id))
    names = {c.name for c in candidates}

    assert "Cloud Infrastructure" in names
    assert "Technology" not in names, "an interior node is not a candidate"
    assert "Indirect" not in names
    assert all(len(c.path) == 3 for c in candidates)


def test_template_seeded_nodes_keep_their_curated_keywords(session):
    tree = service.ensure_default_tree(session, "org")
    session.commit()

    candidates = build_candidates_from_tree(_nodes(session, tree.id))
    cloud = next(c for c in candidates if c.code == "6010")
    assert "hosting" in cloud.keywords and "cdn" in cloud.keywords


def test_a_custom_node_matches_on_its_own_words(session):
    """No curated synonyms, so name and description are the whole corpus."""
    tree = service.create_tree(session, "org", "Custom", max_depth=3)
    root = service.add_node(session, tree, "Indirect")
    mid = service.add_node(session, tree, "Machinery", parent_id=root.id)
    service.add_node(
        session, tree, "Lathe Tooling", parent_id=mid.id,
        description="carbide inserts and toolholders",
    )
    session.commit()

    candidates = build_candidates_from_tree(_nodes(session, tree.id))
    match = categorize("Carbide inserts for the lathe", None, candidates)

    assert match.matched
    assert match.level_3 == "Lathe Tooling"
    assert match.spend_category_id is not None


def test_default_candidates_come_from_the_template(session):
    """The no-database corpus and a seeded tree must describe the same taxonomy."""
    tree = service.ensure_default_tree(session, "org")
    session.commit()

    from_template = {c.path for c in default_candidates()}
    from_tree = {c.path for c in build_candidates_from_tree(_nodes(session, tree.id))}
    assert from_template == from_tree


# -- A match carries its node ------------------------------------------------


def test_a_match_carries_the_node_id(session):
    tree = service.ensure_default_tree(session, "org")
    session.commit()
    candidates = build_candidates_from_tree(_nodes(session, tree.id))

    match = categorize("Cloud server monthly hosting", None, candidates)

    assert match.matched
    node = session.get(SpendCategory, match.spend_category_id)
    assert node is not None and node.name == "Cloud Infrastructure"
    # No `(level_2, level_3)` lookup: the node the matcher chose *is* the answer.
    assert (match.level_1, match.level_2, match.level_3) == (
        "Indirect", "Technology", "Cloud Infrastructure"
    )
    assert match.level_4 is None


def test_a_depth_four_match_records_its_leaf(session):
    tree = service.create_tree(session, "org", "Deep", max_depth=4)
    l1 = service.add_node(session, tree, "Indirect")
    l2 = service.add_node(session, tree, "Technology", parent_id=l1.id)
    l3 = service.add_node(session, tree, "Cloud", parent_id=l2.id)
    service.add_node(
        session, tree, "Compute", parent_id=l3.id, description="virtual machine instances",
    )
    session.commit()

    candidates = build_candidates_from_tree(_nodes(session, tree.id))
    match = categorize("Virtual machine instances", None, candidates)

    assert match.matched and match.level_4 == "Compute"


# -- Per-company scoping -----------------------------------------------------


def _company(s: Session, company_id: str, tree_id: str | None):
    s.add(Company(id=company_id, organization_id="org", name=company_id, spend_tree_id=tree_id))
    s.add(Invoice(id=f"inv-{company_id}", company_id=company_id, status="uncategorized"))
    s.add(InvoiceLine(
        id=f"ln-{company_id}", company_id=company_id, invoice_id=f"inv-{company_id}",
        description="Cloud server monthly hosting", status="uncategorized",
    ))
    s.commit()


def test_two_companies_on_different_trees_get_different_candidates(session):
    default = service.ensure_default_tree(session, "org")
    custom = service.create_tree(session, "org", "Custom", max_depth=3)
    l1 = service.add_node(session, custom, "Indirect")
    l2 = service.add_node(session, custom, "IT", parent_id=l1.id)
    service.add_node(session, custom, "Hosting", parent_id=l2.id, description="cloud server")
    session.commit()

    _company(session, "co-default", default.id)
    _company(session, "co-custom", custom.id)

    for company_id, expected in (("co-default", "Technology"), ("co-custom", "IT")):
        candidates = _tree_candidates(session, company_id)
        match = categorize("Cloud server monthly hosting", None, candidates)
        assert match.level_2 == expected, (
            f"{company_id} was categorized against the wrong tree"
        )


def test_a_company_with_no_tree_has_no_candidates(session):
    _company(session, "co", None)
    assert _tree_candidates(session, "co") is None, (
        "there is no fallback taxonomy — a category the customer never chose is "
        "untraceable, and an uncategorized line is the honest outcome"
    )


def test_a_company_with_an_empty_tree_has_no_candidates(session):
    empty = service.create_tree(session, "org", "Empty", max_depth=3)
    session.commit()
    _company(session, "co", empty.id)
    assert _tree_candidates(session, "co") is None


def test_categorization_writes_the_node_onto_the_line(session):
    tree = service.ensure_default_tree(session, "org")
    session.commit()
    _company(session, "co", tree.id)

    candidates = _tree_candidates(session, "co")
    # No integration in this fixture, so drive the invoice scope directly.
    line = session.get(InvoiceLine, "ln-co")
    from ai_api.sync.categorizer import categorize as _cat

    match = _cat(line.description, None, candidates)
    assert match.matched

    node = session.get(SpendCategory, match.spend_category_id)
    assert node.spend_tree_id == tree.id
