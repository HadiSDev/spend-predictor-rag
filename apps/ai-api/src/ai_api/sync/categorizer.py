"""The candidate set a line is categorized against, and the shape of the answer.

**Candidates come from the company's assigned spend tree**, as persisted
``SpendCategory`` rows — never from a table hard-coded here. A taxonomy the
customer cannot see or edit is one they cannot correct, and the default tree is
now a template they own a copy of (``web_api.spend_trees.template``), reached
through the one-way ``ai_api → web_api`` dependency.

The keyword matcher that used to live here is **gone**, not disabled. It scored
token overlap between a description and a leaf's English name, which on a real
ledger scored zero on almost everything — descriptions arrive in Danish, as brand
strings, or empty — and its one match on live data was ``Company Free plan fee``
→ *Telecom*, because ``plan`` is a telecom keyword and the line is a bank fee. A
wrong category is worse than an honest backlog, so there is no fallback matcher
to fall back to. Categorization is :mod:`ai_api.sync.llm_categorizer`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    """A candidate spend-tree node the categorizer can choose.

    Carries the node's **id**, so a match resolves ``spend_category_id``
    directly. The old shape keyed nodes by ``(level_2, level_3)`` and made the
    runner look the pair back up — which silently produced a null pointer for
    every node the lookup missed.
    """

    node_id: str | None
    #: The node's materialized path, shallowest first, trailing levels dropped.
    path: tuple[str, ...]
    #: The node's own label — what a rationale should name.
    name: str
    code: str | None = None
    description: str | None = None

    def level(self, index: int) -> str | None:
        return self.path[index] if index < len(self.path) else None

    @property
    def sort_key(self) -> tuple:
        """Deterministic tie-break: by code when present, else by path."""
        return (self.code or "￿", self.path)


@dataclass(frozen=True)
class CategoryMatch:
    """Result of categorizing one line."""

    matched: bool
    spend_category_id: str | None
    account_code: str | None
    account_name: str | None
    level_1: str | None
    level_2: str | None
    level_3: str | None
    level_4: str | None
    confidence: float
    rationale: str
    gt_level_1: str | None
    gt_level_2: str | None
    gt_level_3: str | None
    gt_account_code: str | None


def build_candidates_from_tree(nodes) -> list[Category]:
    """Candidates from a tree's persisted ``SpendCategory`` rows.

    **Leaves only.** An interior node is a heading, and matching a line to
    ``Technology`` when the tree offers ``Technology > Software`` throws away the
    precision the customer built the tree for. A node with no children is a leaf
    whatever its depth, so a three-level branch of a four-level tree still
    categorizes.
    """
    parents = {node.parent_id for node in nodes if node.parent_id}
    candidates: list[Category] = []
    for node in nodes:
        if node.id in parents:
            continue
        path = tuple(
            value for value in
            (node.level_1, node.level_2, node.level_3, node.level_4)
            if value is not None
        )
        candidates.append(Category(
            node_id=node.id,
            path=path or (node.name,),
            name=node.name,
            code=node.code,
            description=node.description,
        ))
    return candidates


def default_candidates() -> list[Category]:
    """Candidates built from the platform template, with no database.

    The template's own definition, so this and a seeded tree cannot disagree
    about what the built-in taxonomy is. Used by tests and by any caller that
    has no tree to hand — never by the sync, which refuses to categorize against
    a taxonomy the customer never chose.
    """
    from web_api.spend_trees.template import DEFAULT_TEMPLATE

    interior = {node.path[:-1] for node in DEFAULT_TEMPLATE if node.depth > 1}
    return [
        Category(
            node_id=None,
            path=node.path,
            name=node.name,
            code=node.code,
            description=node.description,
        )
        for node in DEFAULT_TEMPLATE
        if node.path not in interior
    ]


def _gt_fields(native_account_code: str | None, candidates: list[Category]):
    """Ground truth derived from the ERP's own account code for the line.

    Synthetic only: it reads the code off the *mock* chart of accounts and finds
    the template node that carries the same code. Real data has no ground truth
    but a human's verification.
    """
    if not native_account_code:
        return None, None, None, None
    code = str(native_account_code)
    match = next((c for c in candidates if c.code == code), None)
    if match is None:
        return None, None, None, code
    return match.level(0), match.level(1), match.level(2), code


def _worth_narrowing(tree_size: int, top_k: int) -> bool:
    """Is narrowing worth an embedding call?

    Borrowed from the reference implementation's ``tree_size < 2 * top_k``
    bypass: narrowing a 26-leaf tree to 15 spends a round trip to remove eleven
    candidates and risks removing the right one, which is a bad trade in both
    directions.
    """
    return tree_size >= 2 * top_k


def _siblings_of(candidate: Category, all_candidates: list[Category]) -> list[Category]:
    """Every candidate sharing this one's parent path.

    Sibling expansion is what makes retrieval usable rather than merely cheap.
    Embedding a commuter rail ticket finds *Airfare* — it is the only travel leaf
    in a sparse tree — and the answer is *Ground Transport* next to it. Offering
    the hit alone would hand the model a shortlist that excludes the right
    answer and then blame it for the result.
    """
    parent = candidate.path[:-1]
    return [c for c in all_candidates if c.path[:-1] == parent]


def build_candidates_from_retrieval(
    query: str,
    all_candidates: list[Category],
    retrieve,
    *,
    top_k: int = 5,
) -> list[Category]:
    """Narrow ``all_candidates`` to the neighbourhood of the closest nodes.

    ``retrieve`` is the seam: any callable taking ``(query, top_k)`` and
    returning node payloads with a ``spend_category_id``. Tests pass a stub, so
    the suite needs no Qdrant.

    **Never returns fewer candidates than the model can answer from.** Retrieval
    that finds nothing — an unindexed tree, an unreachable vector store, a query
    with no text — yields the full leaf set, not an empty one. An empty candidate
    list is indistinguishable from "this company has no tree", which means "do
    not categorize", and a vector store being down is not a statement about the
    customer's taxonomy.
    """
    if not all_candidates:
        return []
    if not (query or "").strip():
        return list(all_candidates)
    if not _worth_narrowing(len(all_candidates), top_k):
        return list(all_candidates)

    try:
        hits = retrieve(query, top_k)
    except Exception:  # noqa: BLE001 - a retrieval outage is not a taxonomy fact
        return list(all_candidates)

    by_id = {c.node_id: c for c in all_candidates if c.node_id}
    found = [
        by_id[payload["spend_category_id"]]
        for payload in (hits or [])
        if payload.get("spend_category_id") in by_id
    ]
    if not found:
        return list(all_candidates)

    # Order is the tree's, not the retriever's. The prompt numbers candidates and
    # the model answers with a number, so a ranking-ordered list would silently
    # bias the answer toward 1 — and would make the same line's prompt differ
    # between runs, which the cache keys off.
    narrowed = {c.node_id: c for c in found}
    for hit in found:
        for sibling in _siblings_of(hit, all_candidates):
            narrowed[sibling.node_id] = sibling
    return [c for c in all_candidates if c.node_id in narrowed]
