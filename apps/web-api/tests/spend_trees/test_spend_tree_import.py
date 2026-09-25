"""CSV import: validate wholly, then write wholly."""
from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from web_api.db.models import Company, Invoice, InvoiceLine, Organization
from web_api.spend_trees import importer, service

GOOD = """level_1,level_2,level_3,description,code
Indirect,Technology,Cloud Infrastructure,Hosting and compute,6010
Indirect,Technology,Software,Licences,6020
Indirect,Facilities & Office,Utilities,Power and water,6900
Direct,Direct Costs,Cost of Goods Sold,Raw materials,4000
"""


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


def _tree(s: Session, max_depth: int = 3):
    tree = service.create_tree(s, "org", "Imported", max_depth=max_depth)
    s.commit()
    return tree


def _paths(s: Session, tree_id: str):
    return {service.node_path(n) for n in service.tree_nodes(s, tree_id)}


def test_import_materializes_the_implied_interior_nodes(session):
    tree = _tree(session)
    plan = importer.plan_import(session, tree, GOOD)
    result = importer.apply_import(session, tree, plan)
    session.commit()

    paths = _paths(session, tree.id)
    assert ("Indirect",) in paths and ("Direct",) in paths
    assert ("Indirect", "Technology") in paths
    assert ("Indirect", "Technology", "Cloud Infrastructure") in paths
    assert len(paths) == 4 + 2 + 3, f"unexpected node set: {sorted(paths)}"
    assert result["created"] == len(paths)

    leaf = next(
        n for n in service.tree_nodes(session, tree.id) if n.name == "Cloud Infrastructure"
    )
    assert leaf.code == "6010" and leaf.description == "Hosting and compute"
    assert leaf.depth == 3 and leaf.level_1 == "Indirect"


def test_one_bad_row_rejects_the_whole_file(session):
    tree = _tree(session)
    broken = GOOD + "Indirect,,Orphaned Leaf,No parent,9999\n"

    with pytest.raises(importer.ImportRejected) as excinfo:
        importer.plan_import(session, tree, broken)
    session.rollback()

    assert [e.line for e in excinfo.value.errors] == [6]
    assert "skips a level" in excinfo.value.errors[0].message
    assert _paths(session, tree.id) == set(), "a rejected import must write nothing"


def test_an_over_deep_row_is_rejected_with_its_line_number(session):
    tree = _tree(session, max_depth=3)
    deep = "level_1,level_2,level_3,level_4\nIndirect,Technology,Cloud,Compute\n"

    with pytest.raises(importer.ImportRejected) as excinfo:
        importer.plan_import(session, tree, deep)

    assert excinfo.value.errors[0].line == 2
    assert "4 levels deep" in excinfo.value.errors[0].message


def test_a_four_level_row_is_fine_on_a_four_level_tree(session):
    tree = _tree(session, max_depth=4)
    deep = "level_1,level_2,level_3,level_4\nIndirect,Technology,Cloud,Compute\n"
    plan = importer.plan_import(session, tree, deep)
    importer.apply_import(session, tree, plan)
    session.commit()

    leaf = next(n for n in service.tree_nodes(session, tree.id) if n.name == "Compute")
    assert leaf.depth == 4 and leaf.level_4 == "Compute"


def test_duplicate_paths_and_codes_are_reported_per_row(session):
    tree = _tree(session)
    dupes = (
        "level_1,level_2,level_3,code\n"
        "Indirect,Technology,Cloud,6010\n"
        "Indirect,Technology,Cloud,6011\n"
        "Indirect,Technology,Software,6010\n"
    )
    with pytest.raises(importer.ImportRejected) as excinfo:
        importer.plan_import(session, tree, dupes)

    lines = [e.line for e in excinfo.value.errors]
    assert lines == [3, 4], f"both duplicates should be reported, got {excinfo.value.errors}"


def test_a_file_with_no_level_columns_is_rejected(session):
    tree = _tree(session)
    with pytest.raises(importer.ImportRejected) as excinfo:
        importer.plan_import(session, tree, "name,description\nTechnology,x\n")
    assert "No level columns" in excinfo.value.errors[0].message


def test_blank_lines_are_not_errors(session):
    tree = _tree(session)
    plan = importer.plan_import(session, tree, GOOD + ",,,,\n")
    importer.apply_import(session, tree, plan)
    session.commit()
    assert len(_paths(session, tree.id)) == 9


def test_re_importing_the_same_file_updates_in_place(session):
    tree = _tree(session)
    importer.apply_import(session, tree, importer.plan_import(session, tree, GOOD))
    session.commit()
    before = {n.id for n in service.tree_nodes(session, tree.id)}

    changed = GOOD.replace("Hosting and compute", "Cloud spend")
    result = importer.apply_import(session, tree, importer.plan_import(session, tree, changed))
    session.commit()

    after = {n.id for n in service.tree_nodes(session, tree.id)}
    assert after == before, "a re-import must not re-key nodes that lines point at"
    assert result["created"] == 0
    leaf = next(
        n for n in service.tree_nodes(session, tree.id) if n.name == "Cloud Infrastructure"
    )
    assert leaf.description == "Cloud spend"


def test_merge_keeps_nodes_the_file_does_not_mention(session):
    tree = _tree(session)
    importer.apply_import(session, tree, importer.plan_import(session, tree, GOOD))
    session.commit()

    smaller = "level_1,level_2,level_3\nIndirect,Technology,Cloud Infrastructure\n"
    plan = importer.plan_import(session, tree, smaller, mode=importer.MERGE)
    assert plan.removed == []
    importer.apply_import(session, tree, plan)
    session.commit()
    assert ("Indirect", "Facilities & Office", "Utilities") in _paths(session, tree.id)


def test_replace_removes_what_the_file_omits(session):
    tree = _tree(session)
    importer.apply_import(session, tree, importer.plan_import(session, tree, GOOD))
    session.commit()

    smaller = "level_1,level_2,level_3\nIndirect,Technology,Cloud Infrastructure\n"
    plan = importer.plan_import(session, tree, smaller, mode=importer.REPLACE)
    assert {service.node_path(n) for n in plan.removed} == {
        ("Indirect", "Technology", "Software"),
        ("Indirect", "Facilities & Office"),
        ("Indirect", "Facilities & Office", "Utilities"),
        ("Direct",),
        ("Direct", "Direct Costs"),
        ("Direct", "Direct Costs", "Cost of Goods Sold"),
    }
    importer.apply_import(session, tree, plan)
    session.commit()
    assert _paths(session, tree.id) == {
        ("Indirect",), ("Indirect", "Technology"),
        ("Indirect", "Technology", "Cloud Infrastructure"),
    }


def test_replace_reports_the_lines_it_would_orphan(session):
    tree = _tree(session)
    importer.apply_import(session, tree, importer.plan_import(session, tree, GOOD))
    session.commit()

    doomed = next(n for n in service.tree_nodes(session, tree.id) if n.name == "Software")
    session.add(Company(id="co", organization_id="org", name="Co", spend_tree_id=tree.id))
    session.add(Invoice(id="inv", company_id="co", status="verified"))
    session.add(InvoiceLine(
        id="ln", company_id="co", invoice_id="inv", status="verified",
        level_1="Indirect", level_2="Technology", level_3="Software",
        spend_category_id=doomed.id,
    ))
    session.commit()

    smaller = "level_1,level_2,level_3\nIndirect,Technology,Cloud Infrastructure\n"
    plan = importer.plan_import(session, tree, smaller, mode=importer.REPLACE)
    assert [line.id for line in plan.affected_lines] == ["ln"], (
        "the caller must be able to warn before removing categorized nodes"
    )

    result = importer.apply_import(session, tree, plan)
    session.commit()

    assert result["stale_lines"] == 1
    line = session.get(InvoiceLine, "ln")
    assert line.spend_category_id is None
    assert line.level_3 == "Software", "removal clears the pointer, not the decision"
    assert line.status == "verified"
