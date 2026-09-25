"""The candidate set a line is categorized against, and the shape of the answer."""
from __future__ import annotations

from dataclasses import dataclass

from web_api.spend_trees.template import DEFAULT_TEMPLATE


@dataclass(frozen=True)
class Category:
    """A candidate spend-tree node the categorizer can choose."""

    node_id: str | None
    path: tuple[str, ...]
    name: str
    code: str | None = None
    description: str | None = None

    def level(self, index: int) -> str | None:
        return self.path[index] if index < len(self.path) else None

    @property
    def sort_key(self) -> tuple:
        """Deterministic tie-break: coded nodes first by code, then by path."""
        return (not self.code, self.code or "", self.path)


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
    """Candidates from a tree's persisted ``SpendCategory`` rows."""
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
    """Candidates built from the platform template, with no database."""
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
    """Ground truth derived from the ERP's own account code for the line."""
    if not native_account_code:
        return None, None, None, None
    code = str(native_account_code)
    match = next((c for c in candidates if c.code == code), None)
    if match is None:
        return None, None, None, code
    return match.level(0), match.level(1), match.level(2), code


def _worth_narrowing(tree_size: int, top_k: int) -> bool:
    """Is narrowing worth an embedding call?"""
    return tree_size >= 2 * top_k


def _siblings_of(candidate: Category, all_candidates: list[Category]) -> list[Category]:
    """Every candidate sharing this one's parent path."""
    parent = candidate.path[:-1]
    return [c for c in all_candidates if c.path[:-1] == parent]


def build_candidates_from_retrieval(
    query: str,
    all_candidates: list[Category],
    retrieve,
    *,
    top_k: int = 5,
) -> list[Category]:
    """Narrow ``all_candidates`` to the neighbourhood of the closest nodes."""
    if not all_candidates:
        return []
    if not (query or "").strip():
        return list(all_candidates)
    if not _worth_narrowing(len(all_candidates), top_k):
        return list(all_candidates)

    try:
        hits = retrieve(query, top_k)
    except Exception:  # noqa: BLE001
        return list(all_candidates)

    by_id = {c.node_id: c for c in all_candidates if c.node_id}
    found = [
        by_id[payload["spend_category_id"]]
        for payload in (hits or [])
        if payload.get("spend_category_id") in by_id
    ]
    if not found:
        return list(all_candidates)

    narrowed = {c.node_id: c for c in found}
    for hit in found:
        for sibling in _siblings_of(hit, all_candidates):
            narrowed[sibling.node_id] = sibling
    return [c for c in all_candidates if c.node_id in narrowed]
