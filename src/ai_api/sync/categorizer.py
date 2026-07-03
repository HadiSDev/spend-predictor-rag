"""Deterministic keyword categorizer — a stand-in for the Qdrant/LLM categorizer.

The production pipeline embeds each line description, searches the company's
spend tree in Qdrant, and returns the best matching account. Until that
integration lands, the sync runner uses this pure, deterministic keyword
matcher so the end-to-end flow can be exercised and benchmarked.

It scores a line description against a set of candidate spend-tree accounts by
counting shared tokens (account name + curated synonyms), picks the best, and
fills in level_1/level_2/level_3, confidence and a rationale. Ground-truth columns
are derived from the line's native ERP account code when present.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# -- Spend-tree metadata -----------------------------------------------------
# Maps a (mock) chart-of-accounts code to its position in the company spend
# tree plus discriminating keywords. level_1 (Direct/Indirect) is inferred per
# line, not stored on the tree, so it is not part of this table.

_META: dict[str, dict] = {
    "4000": {"name": "Cost of Goods Sold", "l2": "Direct Costs", "l3": "Cost of Goods Sold",
             "kw": {"raw", "materials", "goods", "cogs", "production", "components"}},
    "6010": {"name": "Cloud Hosting & Infrastructure", "l2": "Technology", "l3": "Cloud Infrastructure",
             "kw": {"cloud", "server", "hosting", "cdn", "bandwidth", "database", "instance",
                    "storage", "object", "load", "balancer", "compute"}},
    "6015": {"name": "Third-Party APIs & Data", "l2": "Technology", "l3": "APIs & Data",
             "kw": {"api", "feed", "model", "inference", "integration", "credits", "third-party"}},
    "6020": {"name": "Software Subscriptions", "l2": "Technology", "l3": "Software",
             "kw": {"saas", "license", "software", "subscription", "collaboration", "dev",
                    "tool", "seat", "renewal"}},
    "6030": {"name": "Telecommunications", "l2": "Technology", "l3": "Telecom",
             "kw": {"mobile", "plan", "internet", "fiber", "sip", "trunking", "telecom",
                    "call", "phone"}},
    "6500": {"name": "Office Supplies", "l2": "Facilities & Office", "l3": "Office Supplies",
             "kw": {"paper", "stationery", "toner", "cartridge", "printer", "supplies",
                    "accessories"}},
    "6510": {"name": "Office Equipment", "l2": "Facilities & Office", "l3": "Office Equipment",
             "kw": {"desk", "chair", "monitor", "screen", "equipment", "standing"}},
    "6600": {"name": "Professional Services", "l2": "Professional Services", "l3": "Consulting",
             "kw": {"consulting", "strategy", "workshop", "diligence", "cfo", "management",
                    "interim"}},
    "6610": {"name": "Legal Fees", "l2": "Professional Services", "l3": "Legal",
             "kw": {"legal", "retainer", "contract", "ip", "filing", "compliance", "advisory"}},
    "6620": {"name": "Accounting & Audit", "l2": "Professional Services", "l3": "Accounting",
             "kw": {"bookkeeping", "audit", "tax", "accounting"}},
    "6700": {"name": "Marketing & Advertising", "l2": "Sales & Marketing", "l3": "Marketing",
             "kw": {"social", "media", "campaign", "ads", "google", "content", "blog", "seo",
                    "marketing", "advertising"}},
    "6800": {"name": "Travel - Airfare", "l2": "Travel & Entertainment", "l3": "Airfare",
             "kw": {"airfare", "flight", "trip", "round", "copenhagen", "stockholm", "berlin",
                    "oslo", "london"}},
    "6810": {"name": "Travel - Lodging", "l2": "Travel & Entertainment", "l3": "Lodging",
             "kw": {"hotel", "airbnb", "nights", "apartment", "lodging", "corporate"}},
    "6820": {"name": "Meals & Entertainment", "l2": "Travel & Entertainment", "l3": "Meals",
             "kw": {"dinner", "lunch", "catering", "party", "meals", "entertainment", "client"}},
    "6900": {"name": "Utilities", "l2": "Facilities & Office", "l3": "Utilities",
             "kw": {"electricity", "water", "waste", "gas", "heating", "building",
                    "maintenance", "utilities"}},
    "6910": {"name": "Rent & Lease", "l2": "Facilities & Office", "l3": "Rent & Lease",
             "kw": {"rent", "parking", "lease", "rental", "office"}},
    "7000": {"name": "Shipping & Freight", "l2": "Logistics", "l3": "Shipping",
             "kw": {"package", "delivery", "freight", "courier", "express", "pallet",
                    "shipping", "domestic"}},
    "7050": {"name": "Contractors", "l2": "People", "l3": "Contractors",
             "kw": {"contractor", "freelance", "developer", "designer", "qa", "engineer",
                    "temp", "staff"}},
    "7100": {"name": "Training & Development", "l2": "People", "l3": "Training",
             "kw": {"course", "training", "certification", "exam", "ticket", "online"}},
}

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
    """A candidate spend-tree leaf the categorizer can choose."""

    account_code: str
    account_name: str
    level_2: str
    level_3: str | None
    keywords: frozenset[str]


@dataclass(frozen=True)
class CategoryMatch:
    """Result of categorizing one line."""

    matched: bool
    account_code: str | None
    account_name: str | None
    level_1: str | None
    level_2: str | None
    level_3: str | None
    confidence: float
    rationale: str
    gt_level_1: str | None
    gt_level_2: str | None
    gt_level_3: str | None
    gt_account_code: str | None


def _tokenize(text: str) -> set[str]:
    tokens = set()
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok in _STOPWORDS or _MONTH_SUFFIX_RE.match(tok) or len(tok) < 2:
            continue
        tokens.add(tok)
    return tokens


def _level_1_for(account_code: str | None) -> str | None:
    """Direct/Indirect is inferred, not stored. COGS is the only direct cost here."""
    if account_code is None:
        return None
    return "Direct" if account_code == "4000" else "Indirect"


def default_candidates() -> list[Category]:
    """Candidate set built from the built-in spend-tree metadata."""
    return [
        Category(
            account_code=code,
            account_name=meta["name"],
            level_2=meta["l2"],
            level_3=meta["l3"],
            keywords=frozenset(meta["kw"]),
        )
        for code, meta in _META.items()
    ]


def build_candidates(accounts: list) -> list[Category]:
    """Build candidates from fetched ERP accounts (``ErpAccountData``).

    Expense accounts known to the spend-tree metadata are enriched with curated
    synonyms; unknown expense accounts fall back to their own name tokens with
    level_2 == account name.
    """
    candidates: list[Category] = []
    for acc in accounts:
        if (acc.erp_account_type or "").lower() not in ("expense", ""):
            continue
        code = str(acc.erp_account_code)
        meta = _META.get(code)
        if meta:
            candidates.append(
                Category(code, acc.erp_account_name, meta["l2"], meta["l3"], frozenset(meta["kw"]))
            )
        else:
            candidates.append(
                Category(code, acc.erp_account_name, acc.erp_account_name, None,
                         frozenset(_tokenize(acc.erp_account_name)))
            )
    return candidates or default_candidates()


def _gt_fields(native_account_code: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    """Ground truth derived from the ERP's own account code for the line."""
    if not native_account_code:
        return None, None, None, None
    code = str(native_account_code)
    meta = _META.get(code)
    if not meta:
        return _level_1_for(code), None, None, code
    return _level_1_for(code), meta["l2"], meta["l3"], code


def categorize(
    description: str,
    native_account_code: str | None,
    candidates: list[Category],
) -> CategoryMatch:
    """Match a line description to the best candidate spend-tree account.

    Deterministic: identical inputs always yield an identical result. Ties are
    broken by lowest account code. Returns ``matched=False`` when nothing
    overlaps.
    """
    gt_l1, gt_l2, gt_l3, gt_code = _gt_fields(native_account_code)
    desc_tokens = _tokenize(description or "")

    best: Category | None = None
    best_score = 0
    for cand in sorted(candidates, key=lambda c: c.account_code):
        target = cand.keywords | _tokenize(cand.account_name)
        score = len(desc_tokens & target)
        if score > best_score:
            best_score = score
            best = cand

    if best is None or best_score == 0:
        return CategoryMatch(
            matched=False, account_code=None, account_name=None,
            level_1=None, level_2=None, level_3=None,
            confidence=0.0, rationale="No spend-tree account matched the description.",
            gt_level_1=gt_l1, gt_level_2=gt_l2, gt_level_3=gt_l3, gt_account_code=gt_code,
        )

    overlap = sorted(desc_tokens & (best.keywords | _tokenize(best.account_name)))
    confidence = round(min(0.95, 0.4 + 0.18 * best_score), 3)
    rationale = (
        f"Matched {best_score} keyword(s) {overlap} to "
        f"'{best.account_name}' ({best.account_code})."
    )
    return CategoryMatch(
        matched=True,
        account_code=best.account_code,
        account_name=best.account_name,
        level_1=_level_1_for(best.account_code),
        level_2=best.level_2,
        level_3=best.level_3,
        confidence=confidence,
        rationale=rationale,
        gt_level_1=gt_l1, gt_level_2=gt_l2, gt_level_3=gt_l3, gt_account_code=gt_code,
    )
