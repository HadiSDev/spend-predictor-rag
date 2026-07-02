"""Guardrail: ground a categorization in the real chart of accounts.

The model returns an AccountChoice (a leaf pick + a buyer-derived Direct/Indirect).
This module validates the leaf against the chart, fills L2/L3/account_name from the
chart row (snapping to the top retrieved candidate if the code is fabricated), and
carries the model's L1 through unchanged.
"""
from __future__ import annotations

from .models import AccountChoice, CategorizedInvoice


def _enrich(choice: AccountChoice, row: dict) -> CategorizedInvoice:
    return CategorizedInvoice(
        account_code=row["account_code"],
        account_name=row["account_name"],
        level1=choice.level1,
        level2=row["level2"],
        level3=row["level3"],
        confidence=choice.confidence,
        rationale=choice.rationale,
    )


def ground_categorization(
    choice: AccountChoice,
    candidates: list[dict],
    accounts_by_code: dict[str, dict],
) -> tuple[CategorizedInvoice, str]:
    """Return a (categorization, note) grounded in the chart. L2/L3/leaf come from
    the chart; L1 is the model's buyer-derived judgment."""
    code = choice.account_code
    if code in accounts_by_code:
        return _enrich(choice, accounts_by_code[code]), ""

    if candidates:
        top = candidates[0]
        note = f"categorizer returned invalid code '{code}'; snapped to '{top['account_code']}'"
        return _enrich(choice, top), note

    fallback = CategorizedInvoice(
        account_code=code,
        account_name="",
        level1=choice.level1,
        level2="",
        level3="",
        confidence=choice.confidence,
        rationale=choice.rationale,
    )
    return fallback, f"categorizer returned invalid code '{code}' (no candidates to snap to)"
