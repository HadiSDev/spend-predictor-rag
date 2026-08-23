"""Keys for the categorizer's answer cache.

Both digests are pure functions of their inputs, and both are deliberately
*narrow*: a key that is too broad serves an answer to a question nobody asked,
and one that is too specific never hits.

**What the question is.** The item text, the supplier and the ledger account —
the three facts that determine the answer. The amount is deliberately excluded:
two DSB tickets at 58,00 and 5.780,00 are the same categorization question, and
keying on the amount would turn a cacheable question into a unique one every time.
The buying company is excluded for a different reason: the tree hash already
distinguishes tenants, since two companies on different trees have different
candidate sets, and two companies on the *same* tree genuinely should share an
answer — that is a bookkeeping firm running one taxonomy across its clients, and
re-asking per client is spending money to get the same reply.

**What the tree hash is.** The candidate set *actually offered*, in a form that
ignores order and depends on nothing but content. Order-independent so a query
change that reshuffles candidates does not invalidate every answer; content-only
so a node id churn does not either.
"""
from __future__ import annotations

import hashlib
import json
import re


def _norm(text: str | None) -> str:
    """Whitespace- and case-insensitive, so trivial restatements collide."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def question_key(
    item_name: str | None,
    description: str | None,
    supplier: str | None,
    native_account_code: str | None,
    supplier_description: str | None = None,
) -> str:
    """A digest of what makes this line the categorization question it is.

    ``supplier_description`` is in the key because it is in the *prompt*, and
    anything that changes the prompt changes the answer. Leaving it out was the
    first version, and it made vendor enrichment silently useless: describing
    "DSB" as Danish State Railways is precisely the change that turns an
    unanswerable line into an obvious one, and a cache keyed without it would
    have kept serving the answer from before anybody knew what DSB was.

    The rule this follows: every prompt input is a key input, except one that
    provably cannot change the answer — which is why the amount is out.
    """
    payload = json.dumps(
        [
            _norm(item_name), _norm(description), _norm(supplier),
            _norm(native_account_code), _norm(supplier_description),
        ],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tree_hash(candidates) -> str:
    """A digest of the candidate set offered, independent of its order.

    Includes each candidate's **path**, not its id: a tree rebuilt by CSV import
    has new ids for the same taxonomy, and invalidating every answer over that
    would be paying to relearn something unchanged. It also includes the
    description, because the model reads it and two nodes that differ only there
    are different questions.
    """
    rows = sorted(
        json.dumps(
            [list(c.path), c.code or "", c.description or ""], ensure_ascii=False
        )
        for c in candidates
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def question_sample(
    item_name: str | None, supplier: str | None, native_account_code: str | None
) -> str:
    """A readable trace of the key, for whoever has to debug this table.

    Never matched on. A cache whose rows are two hex digests is a cache nobody
    can reason about when it starts answering wrongly.
    """
    parts = [p for p in (item_name, supplier, native_account_code) if p]
    return " | ".join(parts)[:200]
