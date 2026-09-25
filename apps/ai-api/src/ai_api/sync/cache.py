"""Keys for the categorizer's answer cache."""
from __future__ import annotations

import hashlib
import json
import re


def _norm(text: str | None) -> str:
    """Collapse whitespace and case."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def question_key(
    item_name: str | None,
    description: str | None,
    supplier: str | None,
    native_account_code: str | None,
    supplier_description: str | None = None,
) -> str:
    """A digest of what makes this line the categorization question it is."""
    payload = json.dumps(
        [
            _norm(item_name), _norm(description), _norm(supplier),
            _norm(native_account_code), _norm(supplier_description),
        ],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tree_hash(candidates) -> str:
    """A digest of the candidate set offered, independent of its order."""
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
    """A readable trace of the key."""
    parts = [p for p in (item_name, supplier, native_account_code) if p]
    return " | ".join(parts)[:200]
