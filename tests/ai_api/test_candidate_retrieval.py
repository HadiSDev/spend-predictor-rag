"""Narrowing a large tree to the neighbourhood of a plausible answer.

Every test here is about a *guard*. Narrowing is invisible when it works and
invisible when it goes wrong — the model simply answers from a shortlist that
did not contain the right category, and the rationale reads like a model
mistake. So the interesting cases are the four ways it must decline to narrow.
"""
from __future__ import annotations

import pytest

from sqlmodel import select

from ai_api.sync.categorizer import Category, build_candidates_from_retrieval


def _leaf(node_id: str, *path: str) -> Category:
    return Category(node_id=node_id, path=path, name=path[-1])


TRAVEL = [
    _leaf("n-air", "Indirect", "Travel", "Airfare"),
    _leaf("n-ground", "Indirect", "Travel", "Ground Transport"),
    _leaf("n-lodging", "Indirect", "Travel", "Lodging"),
]
TECH = [
    _leaf("n-cloud", "Indirect", "Technology", "Cloud"),
    _leaf("n-software", "Indirect", "Technology", "Software"),
]
OTHER = [_leaf(f"n-{i}", "Indirect", "Other", f"Thing {i}") for i in range(20)]
BIG = TRAVEL + TECH + OTHER


def _finding(*node_ids: str):
    calls: list[tuple[str, int]] = []

    def retrieve(query: str, top_k: int):
        calls.append((query, top_k))
        return [{"spend_category_id": node_id} for node_id in node_ids]

    retrieve.calls = calls  # type: ignore[attr-defined]
    return retrieve


# -- What it does -------------------------------------------------------------


def test_a_large_tree_is_narrowed():
    narrowed = build_candidates_from_retrieval("Togbillet", BIG, _finding("n-air"), top_k=3)

    assert len(narrowed) < len(BIG)
    assert all(c in BIG for c in narrowed)


def test_a_hit_brings_its_siblings():
    """The reason narrowing is usable rather than merely cheap.

    Embedding a rail ticket finds `Airfare` — the only travel leaf a sparse tree
    has — and the answer is `Ground Transport` beside it. Offering the hit alone
    hands the model a shortlist without the right answer, then blames it.
    """
    narrowed = build_candidates_from_retrieval("Togbillet", BIG, _finding("n-air"), top_k=3)
    names = {c.name for c in narrowed}

    assert names == {"Airfare", "Ground Transport", "Lodging"}


def test_two_hits_bring_two_neighbourhoods():
    narrowed = build_candidates_from_retrieval(
        "Cloud train", BIG, _finding("n-air", "n-cloud"), top_k=3
    )
    names = {c.name for c in narrowed}

    assert "Ground Transport" in names and "Software" in names


def test_the_order_is_the_trees_not_the_retrievers():
    """The prompt numbers candidates and the model answers with a number, so a
    ranking-ordered list biases the answer toward 1 — and makes the same line's
    prompt differ between runs, which the cache keys off."""
    forward = build_candidates_from_retrieval("x", BIG, _finding("n-air", "n-cloud"), top_k=3)
    reversed_ = build_candidates_from_retrieval("x", BIG, _finding("n-cloud", "n-air"), top_k=3)

    assert [c.node_id for c in forward] == [c.node_id for c in reversed_]


# -- The four refusals --------------------------------------------------------


def test_a_small_tree_is_not_narrowed():
    """Narrowing a 5-leaf tree to 3 spends a round trip to remove two candidates
    and risks removing the right one. A bad trade in both directions."""
    small = TRAVEL + TECH
    retrieve = _finding("n-air")

    narrowed = build_candidates_from_retrieval("Togbillet", small, retrieve, top_k=5)

    assert narrowed == small
    assert retrieve.calls == [], "no embedding call is made either"


def test_an_empty_retrieval_yields_the_whole_tree():
    """An unindexed tree is not a statement that the taxonomy is empty. An empty
    candidate list means "do not categorize", which is a different thing."""
    narrowed = build_candidates_from_retrieval("Togbillet", BIG, _finding(), top_k=3)

    assert narrowed == BIG


def test_a_retrieval_failure_yields_the_whole_tree():
    """A vector store being down says nothing about the customer's taxonomy."""
    def exploding(query: str, top_k: int):
        raise ConnectionError("qdrant unreachable")

    narrowed = build_candidates_from_retrieval("Togbillet", BIG, exploding, top_k=3)

    assert narrowed == BIG


def test_a_line_with_no_text_is_not_narrowed():
    """There is nothing to embed, so any shortlist would be arbitrary — and a
    line with no text is exactly the one that most needs the whole tree."""
    retrieve = _finding("n-air")

    narrowed = build_candidates_from_retrieval("   ", BIG, retrieve, top_k=3)

    assert narrowed == BIG
    assert retrieve.calls == []


# -- Scoping ------------------------------------------------------------------


def test_a_hit_outside_the_offered_set_is_ignored():
    """The index is keyed by tree, but a stale index could name a node that has
    since been deleted. It resolves to nothing rather than to a neighbour."""
    narrowed = build_candidates_from_retrieval(
        "x", BIG, _finding("n-air", "n-deleted"), top_k=3
    )

    assert all(c.node_id in {c2.node_id for c2 in BIG} for c in narrowed)
    assert {c.name for c in narrowed} == {"Airfare", "Ground Transport", "Lodging"}


def test_no_candidates_stays_no_candidates():
    assert build_candidates_from_retrieval("x", [], _finding("n-air")) == []


# -- Through the runner -------------------------------------------------------


def test_indexing_swallows_a_vector_store_failure(engine, make_tenant, monkeypatch):
    """The real guard, not a patched stand-in for it.

    Qdrant being down, absent or out of disk is not a reason to stop a ledger
    sync. Patches the module `_index_tree` actually imports from, so the
    try/except under test is the one that runs.
    """
    from sqlmodel import Session

    from ai_api.rag import indexer
    from ai_api.sync import runner
    from web_api.db.models import Company
    from web_api.spend_trees import service

    tenant = make_tenant("Acme")
    with Session(engine) as s:
        company = s.get(Company, tenant["company_id"])
        tree = service.ensure_default_tree(s, company.organization_id)
        company.spend_tree_id = tree.id
        s.add(company)
        s.commit()

    def unreachable(*args, **kwargs):
        raise ConnectionError("qdrant unreachable")

    monkeypatch.setattr(indexer, "build_tree_index", unreachable)

    with Session(engine) as s:
        runner._index_tree(s, tenant["company_id"])  # must not raise


def test_a_sync_categorizes_with_the_whole_tree_when_retrieval_is_down(
    engine, make_tenant, monkeypatch
):
    """The ledger is the point; narrowing is an optimization."""
    from sqlmodel import Session

    from ai_api.rag import indexer
    from ai_api.sync import llm_categorizer, runner
    from web_api.db.models import Company, InvoiceLine
    from web_api.spend_trees import service

    tenant = make_tenant("Acme")
    with Session(engine) as s:
        company = s.get(Company, tenant["company_id"])
        tree = service.ensure_default_tree(s, company.organization_id)
        company.spend_tree_id = tree.id
        s.add(company)
        s.commit()

    def unreachable(*args, **kwargs):
        raise ConnectionError("qdrant unreachable")

    seen: list[str] = []

    def capture(prompt: str) -> str:
        seen.append(prompt)
        return '{"choice": 1, "confidence": 0.9, "rationale": "stub"}'

    monkeypatch.setattr(indexer, "build_tree_index", unreachable)
    monkeypatch.setattr(indexer, "retrieve_categories", unreachable)
    monkeypatch.setattr(llm_categorizer, "_default_complete", capture)

    result = runner.run_sync()

    assert result[tenant["integration_id"]]["status"] == "ok"
    with Session(engine) as s:
        line = s.exec(select(InvoiceLine)).first()
        assert line.status == "ai_categorized"
    # Every leaf was offered — the degradation, not a shortened list.
    numbered = seen[0].split("Categories:", 1)[1]
    assert "Ground Transport" in numbered and "Cost of Goods Sold" in numbered
