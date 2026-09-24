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
    ErpAccount,
    ErpEntry,
    ErpIntegration,
    Invoice,
    InvoiceLine,
    Organization,
    SpendCategory,
)
from web_api.spend_trees import service
from ai_api.sync.categorizer import build_candidates_from_tree, default_candidates
from ai_api.sync.llm_categorizer import LineContext, categorize_line
from ai_api.sync.runner import _categorize_pending, _tree_candidates


def _choosing(fragment: str):
    """A stubbed model that picks the candidate whose path mentions ``fragment``.

    These tests are about *which tree* a company is categorized against and
    whether the chosen node resolves inside it — not about a model's judgment.
    Stubbing the choice keeps them offline and deterministic while still driving
    the real prompt-building and grounding.
    """
    import re as _re

    def complete(prompt: str) -> str:
        for raw in prompt.split("Categories:", 1)[-1].splitlines():
            match = _re.match(r"\s*(\d+)\.\s+(.*)", raw)
            if match and fragment.lower() in match.group(2).lower():
                return f'{{"choice": {match.group(1)}, "confidence": 0.9, "rationale": "stub"}}'
        return '{"choice": 0, "confidence": 0.0, "rationale": "stub found no such candidate"}'

    return complete



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


def test_a_custom_node_is_a_candidate_like_any_other(session):
    """A node the customer wrote is offered to the model exactly as a seeded one.

    Under the keyword matcher a custom node matched worse than a template one,
    because only template nodes carried curated synonyms. The model reads the
    node's own words, so that asymmetry is gone.
    """
    tree = service.create_tree(session, "org", "Custom", max_depth=3)
    root = service.add_node(session, tree, "Indirect")
    mid = service.add_node(session, tree, "Machinery", parent_id=root.id)
    service.add_node(
        session, tree, "Lathe Tooling", parent_id=mid.id,
        description="carbide inserts and toolholders",
    )
    session.commit()

    candidates = build_candidates_from_tree(_nodes(session, tree.id))
    match = categorize_line(
        LineContext(item_name="Carbide inserts for the lathe"), candidates,
        complete=_choosing("Lathe Tooling"),
    )

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

    match = categorize_line(
        LineContext(item_name="Cloud server monthly hosting"), candidates,
        complete=_choosing("Cloud"),
    )

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
    match = categorize_line(
        LineContext(item_name="Virtual machine instances"), candidates,
        complete=_choosing("Compute"),
    )

    assert match.matched and match.level_4 == "Compute"


# -- Per-company scoping -----------------------------------------------------


def _company(s: Session, company_id: str, tree_id: str | None):
    """A company with one invoice, one line, and the ERP scaffolding that makes
    the line reachable from `_categorize_pending`.

    The integration, account and posting are here rather than in the one test
    that needs them because the runner scopes its work through them: an invoice
    belongs to an integration only by way of an entry that references it. A test
    that skips that scaffolding has to reach past the runner to reach the line,
    and reaching past the runner is what let the prompt lose the line's text.
    """
    s.add(Company(id=company_id, organization_id="org", name=company_id, spend_tree_id=tree_id))
    s.add(Invoice(id=f"inv-{company_id}", company_id=company_id, status="uncategorized"))
    s.add(InvoiceLine(
        id=f"ln-{company_id}", company_id=company_id, invoice_id=f"inv-{company_id}",
        item_name="Cloud server monthly hosting", status="uncategorized",
        native_account_code="6010",
    ))
    s.add(ErpIntegration(id=f"erp-{company_id}", company_id=company_id, erp_type="fake"))
    s.add(ErpAccount(
        id=f"acct-{company_id}", company_id=company_id,
        erp_integration_id=f"erp-{company_id}",
        erp_account_code="6010", erp_account_name="Cloud Hosting",
    ))
    s.add(ErpEntry(
        id=f"ent-{company_id}", company_id=company_id,
        erp_account_id=f"acct-{company_id}", erp_entry_id=f"E-{company_id}",
        source_invoice_id=f"inv-{company_id}", entry_type="purchase_invoice",
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
        match = categorize_line(
        LineContext(item_name="Cloud server monthly hosting"), candidates,
        complete=_choosing("Cloud"),
    )
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


def test_categorization_writes_the_node_onto_the_line(session, monkeypatch):
    """Driven through `_categorize_pending`, not around it.

    This test used to build its own `LineContext` from the line — mirroring the
    runner's mapping rather than exercising it — and so it agreed with the
    runner when the runner stopped reading the field the text had moved to.
    A test that restates the code under test cannot disagree with it.
    """
    from ai_api.sync import llm_categorizer

    tree = service.ensure_default_tree(session, "org")
    session.commit()
    _company(session, "co", tree.id)

    seen: list[str] = []

    def _capture(prompt: str) -> str:
        seen.append(prompt)
        return '{"choice": 1, "confidence": 0.9, "rationale": "stub"}'

    monkeypatch.setattr(llm_categorizer, "_default_complete", _capture)

    _categorize_pending(session, "erp-co", "co", _tree_candidates(session, "co"))

    line = session.get(InvoiceLine, "ln-co")
    assert line.status == "ai_categorized"
    node = session.get(SpendCategory, line.spend_category_id)
    assert node.spend_tree_id == tree.id
    # The line's own words reached the model, from the field they are stored in.
    assert "Cloud server monthly hosting" in seen[0].split("Categories:", 1)[0]


# -- Doubt is a number, not a status -----------------------------------------


def _run_with(session, monkeypatch, reply: str):
    """Categorize the fixture company's one line with a scripted model reply."""
    from ai_api.sync import llm_categorizer

    monkeypatch.setattr(llm_categorizer, "_default_complete", lambda prompt: reply)
    _categorize_pending(session, "erp-co", "co", _tree_candidates(session, "co"))
    return session.get(InvoiceLine, "ln-co")


def test_a_hard_line_is_categorized_with_low_confidence_not_failed(session, monkeypatch):
    """The model answering "this is the closest of a poor set" is an answer.

    Recorded as `ai_failed` it would read to a reviewer as a broken categorizer,
    point at no remedy, and never be retried — the sync only processes
    `uncategorized` lines. Recorded as a low confidence it lands in the review
    queue, where the remedy is a person looking at it.
    """
    tree = service.ensure_default_tree(session, "org")
    session.commit()
    _company(session, "co", tree.id)

    line = _run_with(
        session, monkeypatch,
        '{"choice": 1, "confidence": 0.25, "rationale": "Closest of a poor set."}',
    )

    assert line.status == "ai_categorized"
    assert float(line.confidence) == 0.25
    assert line.error_message is None
    assert line.spend_category_id is not None


def test_every_categorized_line_carries_a_confidence(session, monkeypatch):
    """Load-bearing now, not informational: it is what the review filter selects
    on and what the tree-gap suggester reads. A null would be indistinguishable
    from certainty."""
    tree = service.ensure_default_tree(session, "org")
    session.commit()
    _company(session, "co", tree.id)

    line = _run_with(
        session, monkeypatch,
        '{"choice": 1, "confidence": 0.9, "rationale": "Plainly this."}',
    )

    assert line.confidence is not None
    assert 0.0 <= float(line.confidence) <= 1.0


def test_an_unoffered_index_is_still_a_failure(session, monkeypatch):
    """`ai_failed` keeps a meaning, and it is a fault: the model named something
    we never showed it. Snapping to the nearest candidate is what turns a misread
    list into a confident wrong category."""
    tree = service.ensure_default_tree(session, "org")
    session.commit()
    _company(session, "co", tree.id)

    line = _run_with(
        session, monkeypatch,
        '{"choice": 999, "confidence": 0.9, "rationale": "Confident."}',
    )

    assert line.status == "ai_failed"
    assert line.spend_category_id is None
    assert line.level_1 is None
