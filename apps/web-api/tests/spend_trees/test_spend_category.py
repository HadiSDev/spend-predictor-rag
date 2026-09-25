"""SpendTree / SpendCategory ORM: the org-owned tree and its nodes."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from web_api.db.models import Company, Organization, SpendCategory, SpendTree
from web_api.db.models.enums import SpendTreeSource


def _engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(e)
    return e


def _seeded():
    """An org with a 4-level tree holding Indirect > Technology > Cloud > Compute."""
    e = _engine()
    with Session(e) as s:
        s.add(Organization(id="o1", name="Org"))
        s.add(SpendTree(id="t1", organization_id="o1", name="Group tree", max_depth=4))
        s.add(Company(id="c1", organization_id="o1", name="Co", spend_tree_id="t1"))
        s.add(SpendCategory(
            id="n1", spend_tree_id="t1", parent_id=None, depth=1, name="Indirect",
            level_1="Indirect",
        ))
        s.add(SpendCategory(
            id="n2", spend_tree_id="t1", parent_id="n1", depth=2, name="Technology",
            level_1="Indirect", level_2="Technology",
        ))
        s.add(SpendCategory(
            id="n3", spend_tree_id="t1", parent_id="n2", depth=3, name="Cloud",
            level_1="Indirect", level_2="Technology", level_3="Cloud",
        ))
        s.add(SpendCategory(
            id="n4", spend_tree_id="t1", parent_id="n3", depth=4, name="Compute",
            level_1="Indirect", level_2="Technology", level_3="Cloud", level_4="Compute",
            description="cloud servers",
        ))
        s.commit()
    return e


def test_tree_belongs_to_an_organization_and_companies_point_at_it():
    e = _seeded()
    with Session(e) as s:
        org = s.get(Organization, "o1")
        assert [t.name for t in org.spend_trees] == ["Group tree"]
        co = s.get(Company, "c1")
        assert co.spend_tree is not None and co.spend_tree.id == "t1"
        assert {c.name for c in co.spend_tree.categories} == {
            "Indirect", "Technology", "Cloud", "Compute"
        }


def test_two_companies_share_one_tree():
    e = _seeded()
    with Session(e) as s:
        s.add(Company(id="c2", organization_id="o1", name="Co 2", spend_tree_id="t1"))
        s.commit()
        tree = s.get(SpendTree, "t1")
        assert {c.id for c in tree.companies} == {"c1", "c2"}


def test_node_stores_parentage_and_the_materialized_path():
    e = _seeded()
    with Session(e) as s:
        leaf = s.exec(select(SpendCategory).where(SpendCategory.name == "Compute")).one()
        assert leaf.depth == 4
        assert leaf.parent is not None and leaf.parent.name == "Cloud"
        assert (leaf.level_1, leaf.level_2, leaf.level_3, leaf.level_4) == (
            "Indirect", "Technology", "Cloud", "Compute"
        )


def test_depth_one_node_has_only_level_1():
    e = _seeded()
    with Session(e) as s:
        root = s.exec(select(SpendCategory).where(SpendCategory.depth == 1)).one()
        assert root.level_1 == "Indirect"
        assert root.level_2 is None and root.level_3 is None and root.level_4 is None
        assert root.parent_id is None


def test_no_company_id_on_the_node():
    cols = set(SpendCategory.__table__.columns.keys())
    assert "company_id" not in cols, "a node belongs to a tree, not a company"
    assert {"spend_tree_id", "parent_id", "depth", "name", "code", "sort_order"} <= cols
    assert {"level_1", "level_2", "level_3", "level_4"} <= cols
    assert "account_code" not in cols and "account_name" not in cols


def test_sibling_names_are_unique_under_one_parent():
    e = _seeded()
    with Session(e) as s:
        s.add(SpendCategory(
            spend_tree_id="t1", parent_id="n2", depth=3, name="Cloud",
            level_1="Indirect", level_2="Technology", level_3="Cloud",
        ))
        with pytest.raises(IntegrityError):
            s.commit()


def test_the_same_name_under_different_parents_is_fine():
    e = _seeded()
    with Session(e) as s:
        s.add(SpendCategory(
            id="n5", spend_tree_id="t1", parent_id=None, depth=1, name="Direct",
            level_1="Direct",
        ))
        s.add(SpendCategory(
            id="n6", spend_tree_id="t1", parent_id="n5", depth=2, name="Cloud",
            level_1="Direct", level_2="Cloud",
        ))
        s.commit()
        assert len(s.exec(select(SpendCategory).where(SpendCategory.name == "Cloud")).all()) == 2


def test_code_is_unique_within_a_tree():
    e = _seeded()
    with Session(e) as s:
        s.exec(select(SpendCategory).where(SpendCategory.id == "n4")).one().code = "6010"
        s.commit()
        s.add(SpendCategory(
            spend_tree_id="t1", parent_id="n3", depth=4, name="Storage", code="6010",
            level_1="Indirect", level_2="Technology", level_3="Cloud", level_4="Storage",
        ))
        with pytest.raises(IntegrityError):
            s.commit()


def test_tree_source_and_archive_flag():
    e = _seeded()
    with Session(e) as s:
        tree = s.get(SpendTree, "t1")
        assert tree.source == SpendTreeSource.CUSTOM
        assert tree.archived_at is None
        assert tree.template_version is None
        assert SpendTree.__tablename__ == "spend_trees"
