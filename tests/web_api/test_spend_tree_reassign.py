"""Changing a company's spend tree must cost no categorization work.

The whole feature turns on this: a customer who switches taxonomies must not
lose a single human verification, and must be told exactly how many lines now
need a fresh decision.
"""
from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from web_api.db.models import AuditLog, Company, Invoice, InvoiceLine, Organization
from web_api.spend_trees import service
from web_api.spend_trees.reassign import REASSIGN_ACTION, count_stale, reassign_company_tree


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


def _tree_with_technology(s: Session, name: str, leaf: str = "Cloud"):
    """A tree holding Indirect > Technology > <leaf>, returning (tree, leaf node)."""
    tree = service.create_tree(s, "org", name, max_depth=4)
    l1 = service.add_node(s, tree, "Indirect")
    l2 = service.add_node(s, tree, "Technology", parent_id=l1.id)
    node = service.add_node(s, tree, leaf, parent_id=l2.id)
    s.commit()
    return tree, node


def _company_with_line(s: Session, tree_id: str, node_id: str, status: str = "verified"):
    s.add(Company(id="co", organization_id="org", name="Co", spend_tree_id=tree_id))
    s.add(Invoice(id="inv", company_id="co", status="verified"))
    s.add(InvoiceLine(
        id="ln", company_id="co", invoice_id="inv", status=status,
        level_1="Indirect", level_2="Technology", level_3="Cloud",
        confidence=None, rationale="matched on 'cloud'",
        spend_category_id=node_id,
    ))
    s.commit()


def test_a_missing_counterpart_goes_stale_without_losing_anything(session):
    old, old_leaf = _tree_with_technology(session, "Old")
    new, _ = _tree_with_technology(session, "New", leaf="Hosting")
    _company_with_line(session, old.id, old_leaf.id)

    stale = reassign_company_tree(session, "co", old.id, new.id)
    session.commit()

    assert stale == 1
    line = session.get(InvoiceLine, "ln")
    assert line.spend_category_id is None
    assert (line.level_1, line.level_2, line.level_3) == ("Indirect", "Technology", "Cloud"), (
        "the stored decision is the evidence and must survive"
    )
    assert line.status == "verified", "a human verification is never discarded"
    assert line.rationale == "matched on 'cloud'"


def test_an_identical_path_re_resolves(session):
    old, old_leaf = _tree_with_technology(session, "Old")
    new, new_leaf = _tree_with_technology(session, "New")
    _company_with_line(session, old.id, old_leaf.id)

    stale = reassign_company_tree(session, "co", old.id, new.id)
    session.commit()

    assert stale == 0, "a line whose path exists in the new tree needs no review"
    line = session.get(InvoiceLine, "ln")
    assert line.spend_category_id == new_leaf.id
    assert line.spend_category_id != old_leaf.id


def test_matching_is_exact_not_fuzzy(session):
    """A near-miss must go stale, not be quietly re-pointed at something else."""
    old, old_leaf = _tree_with_technology(session, "Old")
    new, _ = _tree_with_technology(session, "New", leaf="cloud")  # lower-case
    _company_with_line(session, old.id, old_leaf.id)

    stale = reassign_company_tree(session, "co", old.id, new.id)
    session.commit()

    assert stale == 1
    assert session.get(InvoiceLine, "ln").spend_category_id is None


def test_nothing_is_requeued_for_categorization(session):
    old, old_leaf = _tree_with_technology(session, "Old")
    new, _ = _tree_with_technology(session, "New", leaf="Hosting")
    _company_with_line(session, old.id, old_leaf.id, status="ai_categorized")

    reassign_company_tree(session, "co", old.id, new.id)
    session.commit()

    assert session.get(InvoiceLine, "ln").status == "ai_categorized", (
        "a reassignment is not a re-categorization trigger"
    )


def test_the_change_is_audited(session):
    old, old_leaf = _tree_with_technology(session, "Old")
    new, _ = _tree_with_technology(session, "New", leaf="Hosting")
    _company_with_line(session, old.id, old_leaf.id)

    reassign_company_tree(session, "co", old.id, new.id)
    session.commit()

    entries = session.exec(
        select(AuditLog).where(AuditLog.entity_id == "ln")
    ).all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.action == REASSIGN_ACTION
    assert entry.actor == "system"
    fields = {c["field"]: c for c in entry.changes}
    assert fields["spend_category_id"]["old"] == old_leaf.id
    assert fields["spend_category_id"]["new"] is None
    assert fields["spend_tree_id"] == {"field": "spend_tree_id", "old": old.id, "new": new.id}


def test_a_re_resolved_line_is_not_audited_as_a_no_op(session):
    """A line that lands on the same id has not changed; it gets no audit row."""
    old, old_leaf = _tree_with_technology(session, "Old")
    _company_with_line(session, old.id, old_leaf.id)

    stale = reassign_company_tree(session, "co", old.id, old.id)
    session.commit()

    assert stale == 0
    assert session.exec(select(AuditLog).where(AuditLog.entity_id == "ln")).all() == []


def test_uncategorized_lines_are_untouched(session):
    old, old_leaf = _tree_with_technology(session, "Old")
    new, _ = _tree_with_technology(session, "New", leaf="Hosting")
    session.add(Company(id="co", organization_id="org", name="Co", spend_tree_id=old.id))
    session.add(Invoice(id="inv", company_id="co", status="uncategorized"))
    session.add(InvoiceLine(
        id="ln", company_id="co", invoice_id="inv", status="uncategorized",
    ))
    session.commit()

    assert reassign_company_tree(session, "co", old.id, new.id) == 0
    assert session.exec(select(AuditLog)).all() == []


def test_count_stale_matches_the_read_predicate(session):
    old, old_leaf = _tree_with_technology(session, "Old")
    new, _ = _tree_with_technology(session, "New", leaf="Hosting")
    _company_with_line(session, old.id, old_leaf.id)

    assert count_stale(session, "co") == 0
    reassign_company_tree(session, "co", old.id, new.id)
    session.commit()
    assert count_stale(session, "co") == 1


def test_another_company_is_not_touched(session):
    old, old_leaf = _tree_with_technology(session, "Old")
    new, _ = _tree_with_technology(session, "New", leaf="Hosting")
    _company_with_line(session, old.id, old_leaf.id)
    session.add(Company(id="co2", organization_id="org", name="Co 2", spend_tree_id=old.id))
    session.add(Invoice(id="inv2", company_id="co2", status="verified"))
    session.add(InvoiceLine(
        id="ln2", company_id="co2", invoice_id="inv2", status="verified",
        level_1="Indirect", level_2="Technology", level_3="Cloud",
        spend_category_id=old_leaf.id,
    ))
    session.commit()

    reassign_company_tree(session, "co", old.id, new.id)
    session.commit()

    assert session.get(InvoiceLine, "ln2").spend_category_id == old_leaf.id
