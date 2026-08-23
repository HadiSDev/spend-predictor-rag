"""Categorize one invoice line by asking a model, grounded in the company's tree.

Replaces a keyword matcher that scored token overlap between a line description
and a leaf's English name. That could not work on a real ledger: descriptions
arrive in Danish (``Togbillet``, ``Småanskaffelser``), as brand strings
(``Cloudflare``, ``apple.com/dk``), or empty — and the taxonomy is English nouns.
Its one match on the dev org was ``Company Free plan fee`` → *Telecom*, because
``plan`` is a telecom keyword and the line is a bank fee.

Three rules follow from that failure:

* **The model chooses by index, never by name.** Candidates are numbered and the
  reply is a number. There is no string matching between what the model wrote
  and what we offered, so a near-miss on spelling cannot become a near-miss on
  category. An index we did not offer resolves to nothing — it is never snapped
  to the closest candidate, which is how a misread list becomes a confident
  wrong answer.
* **The model may decline.** ``0`` means no candidate fits. A model forced to
  pick from a tree with no home for the line is precisely what produced the
  Telecom answer above, and an uncategorized line is an honest backlog where a
  wrongly-categorized one is a lie the reports cannot see through.
* **An outage is not a failed line.** A model that cannot be reached, or that
  answers unparseable text, raises :class:`CategorizerUnavailable` so the caller
  can leave the line ``uncategorized`` and retry next run. Marking it
  ``ai_failed`` would bury a whole batch behind a status the sync never revisits.

The prompt carries what a bookkeeper would use, not only the description: the
ERP account it was posted to *and that account's name*, the supplier, and the
amount. Half of Billy's bill lines carry no description at all, and the account
name (``Edb-udgifter / software``) is often the only statement of what was
bought.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, Field

from ..parsing import json_format_hint, parse_model
from .categorizer import Category, CategoryMatch, _gt_fields

logger = logging.getLogger("ai_api.sync")


class CategorizerUnavailable(Exception):
    """The model could not be reached, or did not answer intelligibly.

    Deliberately distinct from a line the model declined to categorize: this one
    says nothing about the line, and the same line may categorize fine on the
    next run.
    """


@dataclass(frozen=True)
class LineContext:
    """What we can tell the model about one line.

    Every field is optional because every field is genuinely absent somewhere: a
    posting-derived line has no description, a journal line has no supplier, and
    an unconverted line has no currency of its own.

    ``item_name`` and ``description`` are **two fields, not one with a fallback**.
    The name is what was bought and is the field that is nearly always present;
    the description is whatever further detail the source printed, and is usually
    null. Coalescing them would silently drop the description on every line that
    carries both — and reading only ``description``, which is what this class did
    until the ``item_name`` migration moved the text, drops the line's only words
    on almost every line there is.
    """

    item_name: str | None = None
    description: str | None = None
    native_account_code: str | None = None
    native_account_name: str | None = None
    supplier: str | None = None
    amount: Decimal | None = None
    currency: str | None = None


class LineCategoryChoice(BaseModel):
    """The model's answer: which numbered candidate, and how sure."""

    choice: int = Field(
        description="Number of the chosen category from the list, or 0 if none fits."
    )
    confidence: float = Field(description="Confidence from 0.0 to 1.0.")
    rationale: str = Field(description="One sentence explaining the choice.")


#: The judgements a bookkeeper applies that a literal reading of the line does
#: not. Each one exists because the surface text points at the wrong answer:
#: an environmental levy on a freight invoice reads as logistics, a pallet from a
#: machine tool supplier reads as machinery, a laptop inside a consulting
#: engagement reads as hardware. Lifted in substance from the reference
#: implementation in `~/repos/groundley-ai`, whose prompt carries the same rules
#: after the same discoveries.
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
    "If no category genuinely fits, answer 0. Do not force a fit: a wrong "
    "category is worse than none, and 0 is a correct answer when the taxonomy "
    "has no home for this line."
)


def _fact_lines(ctx: LineContext) -> list[str]:
    """The line's facts, omitting the ones we do not have.

    Absent fields are left out rather than printed as "None": a list of nulls
    reads to a model as evidence of absence and invites it to explain them.
    """
    facts: list[str] = []
    name = (ctx.item_name or "").strip()
    detail = (ctx.description or "").strip()
    if name:
        facts.append(f"Item: {name}")
    # Only when it says something the name does not. A source that copied the
    # same text into both fields should not have it read back twice as though
    # two independent statements agreed.
    if detail and detail != name:
        facts.append(f"Detail: {detail}")
    if ctx.supplier:
        facts.append(f"Supplier: {ctx.supplier}")
    if ctx.native_account_code or ctx.native_account_name:
        posted = " ".join(
            part for part in (ctx.native_account_code, ctx.native_account_name) if part
        )
        facts.append(f"Posted to ledger account: {posted}")
    if ctx.amount is not None:
        facts.append(f"Amount: {ctx.amount}" + (f" {ctx.currency}" if ctx.currency else ""))
    return facts or ["(no details were recorded for this line)"]


def build_prompt(ctx: LineContext, candidates: list[Category]) -> str:
    """The prompt for one line. Public so a prompt change is reviewable alone."""
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
        "0. None of these fit\n\n"
        # Reasoning is allowed here and nowhere else in the codebase: choosing
        # one of forty categories is a judgement, and a model that may weigh two
        # candidates aloud chooses better than one told to answer immediately.
        # `_extract_json` scans for the outermost braces, so the prose is free.
        + json_format_hint(LineCategoryChoice, allow_reasoning=True)
    )


def _default_complete(prompt: str) -> str:
    """Ask the configured LLM directly.

    A bare completion rather than a CrewAI agent: this is one question with no
    tools and no iteration, and the agent loop only adds latency per line. The
    JSON hint plus :func:`parse_model` is the house strategy — guided decoding
    against vLLM has produced concurrent runaway timeouts here.
    """
    from ..config import get_llm

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
    """Categorize one line against ``candidates``.

    ``complete`` is the seam: any callable taking a prompt and returning the
    model's text. Tests pass a stub, so the suite needs no model running.

    Raises :class:`CategorizerUnavailable` when the model cannot be reached or
    its answer cannot be parsed. Returns an unmatched result when the model
    declines or names a candidate that was not offered.
    """
    if not candidates:
        # No tree, no categorization — and no tokens spent learning that.
        return _no_match("No spend categories are available to choose from.", ctx, candidates)

    ask = complete or _default_complete
    prompt = build_prompt(ctx, candidates)
    try:
        reply = ask(prompt)
    except Exception as exc:  # noqa: BLE001 - any transport failure is an outage
        raise CategorizerUnavailable(str(exc)) from exc

    try:
        choice = parse_model(reply, LineCategoryChoice)
    except Exception as exc:  # noqa: BLE001 - unparseable means the stack is wrong
        raise CategorizerUnavailable(
            f"the categorizer returned no usable answer: {exc}"
        ) from exc

    if choice.choice == 0:
        return _no_match(choice.rationale, ctx, candidates)

    if not 1 <= choice.choice <= len(candidates):
        # Never snapped to the nearest candidate: a model that misread the list
        # would otherwise produce a confident wrong category.
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
        # A model that answers 95 for 95% must not store 95.0 in a 0..1 column.
        confidence=round(min(1.0, max(0.0, float(choice.confidence))), 3),
        rationale=choice.rationale,
        gt_level_1=gt_l1, gt_level_2=gt_l2, gt_level_3=gt_l3, gt_account_code=gt_code,
    )
