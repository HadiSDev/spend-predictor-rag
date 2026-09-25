"""Raising the template version must not reach into anybody's copy."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session, select

from web_api.db.models import Company, InvoiceLine, Organization, SpendCategory, SpendTree
from web_api.spend_trees import service
from web_api.spend_trees.template import DEFAULT_TEMPLATE, TEMPLATE_VERSION


def _paths(s: Session, tree_id: str) -> set[tuple]:
    nodes = s.exec(select(SpendCategory).where(SpendCategory.spend_tree_id == tree_id)).all()
    return {
        tuple(x for x in (n.level_1, n.level_2, n.level_3, n.level_4) if x)
        for n in nodes
    }


@pytest.fixture()
def org(engine):
    with Session(engine) as s:
        organization = Organization(name="Aged Org")
        s.add(organization)
        s.commit()
        yield organization.id


def test_a_commuter_rail_ticket_has_a_home(engine, org):
    with Session(engine) as s:
        tree = service.ensure_default_tree(s, org)
        s.commit()

        assert ("Indirect", "Travel & Entertainment", "Ground Transport") in _paths(s, tree.id)


def test_a_bank_fee_has_a_home_that_is_not_telecom(engine, org):
    with Session(engine) as s:
        tree = service.ensure_default_tree(s, org)
        s.commit()
        paths = _paths(s, tree.id)

        assert ("Indirect", "Financial Services", "Banking & Account Fees") in paths
        assert ("Indirect", "Insurance", "Liability Insurance") in paths


def test_the_template_stays_three_levels_and_two_roots(engine, org):
    with Session(engine) as s:
        tree = service.ensure_default_tree(s, org)
        s.commit()

        assert tree.max_depth == 3
        for path in _paths(s, tree.id):
            assert path[0] in ("Direct", "Indirect")
            assert len(path) <= 3


def test_an_existing_copy_is_untouched_by_a_version_bump(engine, org, monkeypatch):
    monkeypatch.setattr(service, "TEMPLATE_VERSION", "1")
    with Session(engine) as s:
        tree = service.ensure_default_tree(s, org)
        s.commit()
        tree_id = tree.id
        before = _paths(s, tree_id)

    monkeypatch.undo()

    with Session(engine) as s:
        again = service.ensure_default_tree(s, org)
        s.commit()

        assert again.id == tree_id, "a bump must not seed a second copy"
        assert _paths(s, tree_id) == before, "no node added, removed or renamed"
        assert s.get(SpendTree, tree_id).template_version == "1"


def test_a_customers_own_edits_survive_a_reseed(engine, org):
    with Session(engine) as s:
        tree = service.ensure_default_tree(s, org)
        travel = s.exec(
            select(SpendCategory).where(
                SpendCategory.spend_tree_id == tree.id,
                SpendCategory.name == "Travel & Entertainment",
            )
        ).first()
        service.add_node(s, tree, "Scooter Hire", parent_id=travel.id, code="6899")
        s.commit()
        tree_id = tree.id
        before = _paths(s, tree_id)

    with Session(engine) as s:
        service.ensure_default_tree(s, org)
        s.commit()

        assert _paths(s, tree_id) == before
        assert ("Indirect", "Travel & Entertainment", "Scooter Hire") in _paths(s, tree_id)


def test_a_reseed_never_duplicates_a_node(engine, org):
    with Session(engine) as s:
        tree = service.ensure_default_tree(s, org)
        s.commit()
        tree_id = tree.id
        count = len(s.exec(
            select(SpendCategory).where(SpendCategory.spend_tree_id == tree_id)
        ).all())

    with Session(engine) as s:
        service.ensure_default_tree(s, org)
        s.commit()
        after = s.exec(
            select(SpendCategory).where(SpendCategory.spend_tree_id == tree_id)
        ).all()

        assert len(after) == count
        assert len([n for n in after if n.name == "Ground Transport"]) == 1


def test_categorized_lines_are_unaffected(engine, org):
    with Session(engine) as s:
        tree = service.ensure_default_tree(s, org)
        s.commit()
        company = Company(organization_id=org, name="Acme", base_currency="DKK",
                          spend_tree_id=tree.id)
        s.add(company)
        s.commit()
        node = s.exec(
            select(SpendCategory).where(
                SpendCategory.spend_tree_id == tree.id,
                SpendCategory.name == "Software",
            )
        ).first()
        line = InvoiceLine(
            company_id=company.id, invoice_id="inv-x", item_name="Claude",
            amount=Decimal("10.00"), status="ai_categorized",
            spend_category_id=node.id, level_1=node.level_1,
            level_2=node.level_2, level_3=node.level_3,
        )
        s.add(line)
        s.commit()
        line_id, node_id = line.id, node.id

    with Session(engine) as s:
        service.ensure_default_tree(s, org)
        s.commit()
        line = s.get(InvoiceLine, line_id)

        assert line.spend_category_id == node_id
        assert (line.level_1, line.level_2, line.level_3) == ("Indirect", "Technology", "Software")


def test_a_new_organization_gets_the_new_template(engine):
    with Session(engine) as s:
        fresh = Organization(name="Fresh Org")
        s.add(fresh)
        s.commit()

        tree = service.ensure_default_tree(s, fresh.id)
        s.commit()

        assert tree.template_version == TEMPLATE_VERSION
        assert ("Indirect", "Travel & Entertainment", "Ground Transport") in _paths(s, tree.id)
        assert len(_paths(s, tree.id)) == len({n.path for n in DEFAULT_TEMPLATE})
