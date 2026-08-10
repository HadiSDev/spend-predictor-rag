"""Deterministic keyword categorizer — a stand-in for the Qdrant/LLM categorizer.

The production pipeline embeds each line description, searches the company's
spend tree in Qdrant, and returns the best matching node. Until that integration
lands, the sync runner uses this pure, deterministic keyword matcher so the
end-to-end flow can be exercised and benchmarked.

**Candidates come from the company's assigned spend tree**, as persisted
``SpendCategory`` rows. They used to come from ``_META``, a table hard-coded here
and keyed by mock ERP account code — which made the taxonomy invisible to the
customer, uneditable, and identical for every tenant. That table is now the seed
definition of the platform's default tree template
(``web_api.spend_trees.template``), reached through the one-way
``ai_api → web_api`` dependency.

One asymmetry is deliberate and temporary: a **template-seeded** node gets the
template's curated synonyms, matched by its ``code``; a node a customer wrote
themselves matches on its own name and description alone, and so matches less
well. That is a weakness of *this stub matcher*, not of the tree, and it
disappears with the embedding categorizer, which needs no curated synonyms.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from web_api.spend_trees.template import KEYWORDS_BY_CODE

# Generic words that carry no categorization signal.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "per", "of", "to", "monthly", "annual",
    "fee", "fees", "service", "services", "business", "unit", "units", "standard",
    "usage", "rate", "hourly", "daily", "fixed", "full", "day", "production",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MONTH_SUFFIX_RE = re.compile(r"^m\d+$")  # synthetic "(M7)" recurrence markers


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
    keywords: frozenset[str] = field(default_factory=frozenset)

    def level(self, index: int) -> str | None:
        return self.path[index] if index < len(self.path) else None

    @property
    def sort_key(self) -> tuple:
        """Deterministic tie-break: by code when present, else by path."""
        return (self.code or "￿", self.path)

    @property
    def match_text(self) -> frozenset[str]:
        return self.keywords | _tokenize(self.name) | _tokenize(self.description or "")


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


def _tokenize(text: str) -> frozenset[str]:
    tokens = set()
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok in _STOPWORDS or _MONTH_SUFFIX_RE.match(tok) or len(tok) < 2:
            continue
        tokens.add(tok)
    return frozenset(tokens)


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
            keywords=KEYWORDS_BY_CODE.get(node.code or "", frozenset()),
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
            keywords=node.keywords,
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


def categorize(
    description: str,
    native_account_code: str | None,
    candidates: list[Category],
) -> CategoryMatch:
    """Match a line description to the best candidate spend-tree node.

    Deterministic: identical inputs always yield an identical result. Ties are
    broken by the candidate's code, else its path. Returns ``matched=False``
    when nothing overlaps.
    """
    gt_l1, gt_l2, gt_l3, gt_code = _gt_fields(native_account_code, candidates)
    desc_tokens = _tokenize(description or "")

    best: Category | None = None
    best_score = 0
    for cand in sorted(candidates, key=lambda c: c.sort_key):
        score = len(desc_tokens & cand.match_text)
        if score > best_score:
            best_score = score
            best = cand

    if best is None or best_score == 0:
        return CategoryMatch(
            matched=False, spend_category_id=None, account_code=None, account_name=None,
            level_1=None, level_2=None, level_3=None, level_4=None,
            confidence=0.0, rationale="No spend category matched the description.",
            gt_level_1=gt_l1, gt_level_2=gt_l2, gt_level_3=gt_l3, gt_account_code=gt_code,
        )

    overlap = sorted(desc_tokens & best.match_text)
    confidence = round(min(0.95, 0.4 + 0.18 * best_score), 3)
    label = f"'{best.name}'" + (f" ({best.code})" if best.code else "")
    rationale = f"Matched {best_score} keyword(s) {overlap} to {label}."
    return CategoryMatch(
        matched=True,
        spend_category_id=best.node_id,
        account_code=best.code,
        account_name=best.name,
        level_1=best.level(0),
        level_2=best.level(1),
        level_3=best.level(2),
        level_4=best.level(3),
        confidence=confidence,
        rationale=rationale,
        gt_level_1=gt_l1, gt_level_2=gt_l2, gt_level_3=gt_l3, gt_account_code=gt_code,
    )
