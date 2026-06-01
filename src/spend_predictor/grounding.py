"""Guardrail: ground a categorization in the real chart of accounts.

Small LLMs frequently fabricate plausible-but-fake account codes instead of
choosing from the retrieved candidates. This module validates the model's
account code against the actual chart and, when it is invalid, snaps to the
top RAG-retrieved candidate so every ledger row carries a real account code.
"""
from __future__ import annotations

from .models import CategorizedInvoice


def ground_categorization(
    categorized: CategorizedInvoice,
    candidates: list[dict],
    accounts_by_code: dict[str, dict],
) -> tuple[CategorizedInvoice, str]:
    """Return a (categorization, note) pair grounded in the chart of accounts.

    - If the model's ``account_code`` is a real chart account, keep it but
      canonicalize the name and category to the chart's values (the model often
      gets the code right but the label wrong).
    - Otherwise snap code/name/category to the top retrieved candidate and
      record what happened in the returned note.
    """
    code = categorized.account_code
    if code in accounts_by_code:
        acct = accounts_by_code[code]
        corrected = categorized.model_copy(
            update={
                "account_name": acct["account_name"],
                "category": acct["category"],
            }
        )
        return corrected, ""

    if candidates:
        top = candidates[0]
        corrected = categorized.model_copy(
            update={
                "account_code": top["account_code"],
                "account_name": top["account_name"],
                "category": top["category"],
            }
        )
        note = (
            f"categorizer returned invalid code '{code}'; "
            f"snapped to '{top['account_code']}'"
        )
        return corrected, note

    return categorized, f"categorizer returned invalid code '{code}' (no candidates to snap to)"
