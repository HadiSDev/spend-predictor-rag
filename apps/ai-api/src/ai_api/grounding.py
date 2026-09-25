"""Guardrail: ground a categorization in the real chart of accounts."""
from __future__ import annotations

from .models import AccountChoice, CategorizedInvoice


def _enrich(choice: AccountChoice, row: dict) -> CategorizedInvoice:
    return CategorizedInvoice(
        account_code=row["account_code"],
        account_name=row["account_name"],
        level_1=choice.level_1,
        level_2=row["level_2"],
        level_3=row["level_3"],
        confidence=choice.confidence,
        rationale=choice.rationale,
    )


def ground_categorization(
    choice: AccountChoice,
    candidates: list[dict],
    accounts_by_code: dict[str, dict],
) -> tuple[CategorizedInvoice, str]:
    """Return a (categorization, note) grounded in the chart."""
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
        level_1=choice.level_1,
        level_2="",
        level_3="",
        confidence=choice.confidence,
        rationale=choice.rationale,
    )
    return fallback, f"categorizer returned invalid code '{code}' (no candidates to snap to)"
