"""Categorize one invoice line by asking a model, grounded in the company's tree."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, Field

from ..config import get_llm
from ..parsing import json_format_hint, parse_model
from .categorizer import Category, CategoryMatch, _gt_fields

logger = logging.getLogger("ai_api.sync")


class CategorizerUnavailable(Exception):
    """The model could not be reached, or did not answer intelligibly."""


@dataclass(frozen=True)
class LineContext:
    """What we can tell the model about one line."""

    item_name: str | None = None
    description: str | None = None
    native_account_code: str | None = None
    native_account_name: str | None = None
    supplier: str | None = None
    supplier_description: str | None = None
    buyer: str | None = None
    buyer_description: str | None = None
    amount: Decimal | None = None
    currency: str | None = None


class LineCategoryChoice(BaseModel):
    """The model's answer: which numbered candidate, and how sure."""

    choice: int = Field(
        description="Number of the chosen category from the list, or 0 if none fits."
    )
    confidence: float = Field(description="Confidence from 0.0 to 1.0.")
    rationale: str = Field(description="One sentence explaining the choice.")


_ACCOUNTING_RULES = (
    "Apply these rules; they override what the line's wording suggests on its own:\n"
    "- A fee, tax, toll, tariff, duty or environmental levy belongs to fees and "
    "taxes REGARDLESS of which supplier issued it. Freight and shipping are NOT "
    "fees — categorize those as logistics.\n"
    "- Packaging — boxes, pallets, wrapping, crates — belongs to packaging or "
    "supplies regardless of the supplier's main trade.\n"
    "- A product supplied as part of a professional service (consulting, legal, "
    "marketing, design, testing) follows the SERVICE, not the product.\n"
    "- A line that states only a discount or rebate is categorized from the "
    "supplier, since it adjusts whatever that supplier sold."
)

_INSTRUCTIONS = (
    "You are a management accountant categorizing one line of a supplier "
    "invoice into a company's own spend taxonomy.\n"
    "\n"
    "Choose the single best-fitting category from the numbered list. Answer with "
    "its number. Descriptions may be in any language, may be a brand or domain "
    "name, or may be missing entirely — in that case use the ledger account, the "
    "supplier and the amount to decide.\n"
    "\n"
    f"{_ACCOUNTING_RULES}\n"
    "\n"
    "You must return a category, even if it is only an estimate. Express your "
    "doubt in the confidence, not by refusing: 0.9 means the line plainly "
    "belongs there, 0.3 means it is the closest of a poor set. A low-confidence "
    "answer is read by a human; a refusal is read by nobody."
)


def _fact_lines(ctx: LineContext) -> list[str]:
    """The line's facts, omitting the ones we do not have."""
    facts: list[str] = []
    name = (ctx.item_name or "").strip()
    detail = (ctx.description or "").strip()
    if name:
        facts.append(f"Item: {name}")
    if detail and detail != name:
        facts.append(f"Detail: {detail}")
    if ctx.supplier:
        supplier = f"Supplier: {ctx.supplier}"
        if (ctx.supplier_description or "").strip():
            supplier += f" — {ctx.supplier_description.strip()}"
        facts.append(supplier)
    if ctx.buyer:
        buyer = f"Bought by: {ctx.buyer}"
        if (ctx.buyer_description or "").strip():
            buyer += f" — {ctx.buyer_description.strip()}"
        facts.append(buyer)
    if ctx.native_account_code or ctx.native_account_name:
        posted = " ".join(
            part for part in (ctx.native_account_code, ctx.native_account_name) if part
        )
        facts.append(f"Posted to ledger account: {posted}")
    if ctx.amount is not None:
        facts.append(f"Amount: {ctx.amount}" + (f" {ctx.currency}" if ctx.currency else ""))
    return facts or ["(no details were recorded for this line)"]


def build_prompt(ctx: LineContext, candidates: list[Category]) -> str:
    """The prompt for one line."""
    numbered = "\n".join(
        f"{index}. {' > '.join(cand.path)}"
        + (f" — {cand.description}" if cand.description else "")
        for index, cand in enumerate(candidates, start=1)
    )
    facts = "\n".join(_fact_lines(ctx))
    return (
        f"{_INSTRUCTIONS}\n\n"
        f"Invoice line:\n{facts}\n\n"
        f"Categories:\n{numbered}\n\n"
        + json_format_hint(LineCategoryChoice, allow_reasoning=True)
    )


def _default_complete(prompt: str) -> str:
    """Ask the configured LLM directly."""
    return get_llm().call(prompt)


def _no_match(rationale: str, ctx: LineContext, candidates: list[Category]) -> CategoryMatch:
    gt_l1, gt_l2, gt_l3, gt_code = _gt_fields(ctx.native_account_code, candidates)
    return CategoryMatch(
        matched=False, spend_category_id=None, account_code=None, account_name=None,
        level_1=None, level_2=None, level_3=None, level_4=None,
        confidence=0.0, rationale=rationale,
        gt_level_1=gt_l1, gt_level_2=gt_l2, gt_level_3=gt_l3, gt_account_code=gt_code,
    )


def categorize_line(
    ctx: LineContext,
    candidates: list[Category],
    *,
    complete=None,
) -> CategoryMatch:
    """Categorize one line against ``candidates``."""
    if not candidates:
        return _no_match("No spend categories are available to choose from.", ctx, candidates)

    ask = complete or _default_complete
    prompt = build_prompt(ctx, candidates)
    try:
        reply = ask(prompt)
    except Exception as exc:  # noqa: BLE001
        raise CategorizerUnavailable(str(exc)) from exc

    try:
        choice = parse_model(reply, LineCategoryChoice)
    except Exception as exc:  # noqa: BLE001
        raise CategorizerUnavailable(
            f"the categorizer returned no usable answer: {exc}"
        ) from exc

    if not 1 <= choice.choice <= len(candidates):
        logger.warning(
            "categorizer chose %s, outside the %d candidates offered",
            choice.choice, len(candidates),
        )
        return _no_match(
            f"The categorizer chose {choice.choice}, which is not one of the "
            f"{len(candidates)} categories offered.",
            ctx, candidates,
        )

    best = candidates[choice.choice - 1]
    gt_l1, gt_l2, gt_l3, gt_code = _gt_fields(ctx.native_account_code, candidates)
    return CategoryMatch(
        matched=True,
        spend_category_id=best.node_id,
        account_code=best.code,
        account_name=best.name,
        level_1=best.level(0),
        level_2=best.level(1),
        level_3=best.level(2),
        level_4=best.level(3),
        confidence=round(min(1.0, max(0.0, float(choice.confidence))), 3),
        rationale=choice.rationale,
        gt_level_1=gt_l1, gt_level_2=gt_l2, gt_level_3=gt_l3, gt_account_code=gt_code,
    )
