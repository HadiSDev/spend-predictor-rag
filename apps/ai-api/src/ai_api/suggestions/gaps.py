"""Find the categories a company's spend needed and its tree did not have.

The model must now return a category rather than declining, which removes the
old failure mode — a line stranded forever in `ai_failed` — and creates a new
obligation. Something has to notice when the tree is the problem, because the
categorizer no longer says so.

**The signal is a run of low-confidence answers over similar spend.** One line
answered at 0.3 is an odd purchase. Eleven lines from rail and taxi suppliers all
answered at 0.3 is a missing category, and the difference between those two is
the whole judgement this module makes. A tree that grows a node per strange
invoice is worse than one with a gap in it: the gap is at least visible.

**Nothing here writes a `SpendCategory`.** `web_api/spend_trees/service.py` is
the only writer of that table — a rename rewrites every descendant's materialized
path — and acceptance goes through it, invoked by a person. This module writes
proposals and only proposals, which is also what keeps it inside the one-way
`ai_api → web_api` dependency.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from web_api import config as web_config
from web_api.db.models import (
    Company,
    Invoice,
    InvoiceLine,
    SpendCategory,
    SpendCategorySuggestion,
    SuggestionState,
    Vendor,
)

from ..parsing import json_format_hint, parse_model

logger = logging.getLogger("ai_api.suggestions")

#: How many low-confidence lines a group needs before it is a taxonomy claim
#: rather than an odd purchase. Three is the smallest number that can show a
#: pattern; below it the evidence panel would read as one person's bad week.
MIN_GROUP_SIZE = 3

#: A group is formed per supplier. Not by embedding similarity, deliberately:
#: the supplier is the strongest and cheapest signal that two lines are the same
#: kind of spend — every DSB line is travel whatever the ticket says — and it is
#: an argument a reviewer can check at a glance, which an embedding neighbourhood
#: is not.
#:
#: The cost is real and accepted: eight low-confidence lines from eight different
#: one-off suppliers that are all in fact the same gap will not group. That is
#: the conservative direction to fail in.


class GapProposal(BaseModel):
    """The model's answer: what category these lines needed."""

    name: str = Field(description="Short category name, 1-4 words.")
    description: str = Field(description="One sentence on what belongs in it.")
    parent: str = Field(
        description="Which existing top-level or second-level category it belongs under."
    )
    rationale: str = Field(description="One sentence on why the tree needs it.")


@dataclass
class SuggestionRun:
    considered: int = 0
    groups: int = 0
    proposed: int = 0
    already_present: int = 0
    dismissed_before: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def as_dict(self) -> dict:
        return {
            "considered": self.considered,
            "groups": self.groups,
            "proposed": self.proposed,
            "already_present": self.already_present,
            "dismissed_before": self.dismissed_before,
        }


def _normalize(text: str | None) -> str:
    """Compare names the way a person would: case- and punctuation-blind."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def doubtful_lines(
    session: Session, company_id: str, *, threshold: float | None = None
) -> list[InvoiceLine]:
    """The company's AI-categorized lines the model was not confident about.

    The same predicate `GET /invoice-lines?needs_review=true` selects on, and for
    the same reason: these are the decisions nobody should be relying on, and a
    run of them over one supplier is what a missing category looks like from the
    outside.
    """
    if threshold is None:
        threshold = web_config.CATEGORIZATION_REVIEW_THRESHOLD
    lines = session.exec(
        select(InvoiceLine).where(
            InvoiceLine.company_id == company_id,
            InvoiceLine.status == "ai_categorized",
        )
    ).all()
    return [
        line for line in lines
        if line.confidence is None or float(line.confidence) < threshold
    ]


def group_by_supplier(
    session: Session, lines: list[InvoiceLine]
) -> dict[str, list[InvoiceLine]]:
    """Group doubtful lines by the supplier that billed them.

    Lines whose invoice names no supplier are dropped rather than pooled into an
    "unknown" group: they have nothing in common but our ignorance, and a
    proposal argued from them would cite lines that share no property at all.
    """
    invoice_ids = {line.invoice_id for line in lines}
    vendors: dict[str, str | None] = {}
    if invoice_ids:
        for invoice in session.exec(
            select(Invoice).where(Invoice.id.in_(invoice_ids))  # type: ignore[union-attr]
        ).all():
            vendors[invoice.id] = invoice.vendor_id

    grouped: dict[str, list[InvoiceLine]] = {}
    for line in lines:
        vendor_id = vendors.get(line.invoice_id)
        if vendor_id is None:
            continue
        grouped.setdefault(vendor_id, []).append(line)
    return {k: v for k, v in grouped.items() if len(v) >= MIN_GROUP_SIZE}


def _tree_outline(nodes: list[SpendCategory]) -> str:
    """The tree as paths, so the model proposes into a shape it can see."""
    return "\n".join(sorted(
        " > ".join(x for x in (n.level_1, n.level_2, n.level_3, n.level_4) if x)
        for n in nodes
    ))


def build_prompt(
    supplier: str,
    supplier_description: str | None,
    lines: list[InvoiceLine],
    nodes: list[SpendCategory],
) -> str:
    """The prompt for one group. Public so a prompt change is reviewable alone."""
    items = "\n".join(
        f"- {line.item_name or line.description or '(no description)'}"
        + (f" — landed in {line.level_3 or line.level_2 or line.level_1}"
           if (line.level_1 or line.level_2 or line.level_3) else "")
        for line in lines[:20]
    )
    supplier_line = supplier + (f" — {supplier_description}" if supplier_description else "")
    return (
        "You are a management accountant reviewing a company's spend taxonomy.\n"
        "\n"
        f"These {len(lines)} invoice lines from one supplier were all categorized "
        "with low confidence, which usually means the taxonomy has no good home "
        "for this kind of spend.\n"
        "\n"
        f"Supplier: {supplier_line}\n"
        f"Lines:\n{items}\n"
        "\n"
        f"The company's current categories:\n{_tree_outline(nodes)}\n"
        "\n"
        "Propose the ONE category this tree is missing that these lines belong "
        "in. Name an existing category as its parent. If the tree already has a "
        "category that genuinely covers this spend, propose that same name — the "
        "caller checks and discards it, which is the correct outcome when the "
        "problem was the categorizer rather than the taxonomy.\n"
        "\n"
        + json_format_hint(GapProposal, allow_reasoning=True)
    )


def _default_complete(prompt: str) -> str:
    from ..config import get_llm

    return get_llm().call(prompt)


def suggest_gaps(
    session: Session,
    company_id: str,
    *,
    complete=None,
    threshold: float | None = None,
) -> SuggestionRun:
    """Propose the categories ``company_id``'s tree is missing. Writes no nodes.

    ``complete`` is the seam: any callable taking a prompt and returning the
    model's text, so tests need no model running.
    """
    run = SuggestionRun()
    company = session.get(Company, company_id)
    if company is None or company.spend_tree_id is None:
        run.notes.append("no spend tree assigned; nothing to suggest into")
        return run

    nodes = list(session.exec(
        select(SpendCategory).where(
            SpendCategory.spend_tree_id == company.spend_tree_id
        )
    ).all())
    if not nodes:
        run.notes.append("the assigned tree is empty; nothing to suggest into")
        return run

    lines = doubtful_lines(session, company_id, threshold=threshold)
    run.considered = len(lines)
    groups = group_by_supplier(session, lines)
    run.groups = len(groups)
    if not groups:
        return run

    existing_names = {_normalize(n.name) for n in nodes}
    # Every proposal ever settled for this tree, whether accepted or dismissed.
    # Re-proposing a dismissal re-argues a question the customer has answered,
    # and a list that does that is one people stop reading.
    settled = {
        _normalize(row.name)
        for row in session.exec(
            select(SpendCategorySuggestion).where(
                SpendCategorySuggestion.spend_tree_id == company.spend_tree_id
            )
        ).all()
    }
    by_name = {_normalize(n.name): n for n in nodes}
    ask = complete or _default_complete

    for vendor_id, group in groups.items():
        vendor = session.get(Vendor, vendor_id)
        prompt = build_prompt(
            vendor.name if vendor else vendor_id,
            vendor.description if vendor else None,
            group,
            nodes,
        )
        try:
            proposal = parse_model(ask(prompt), GapProposal)
        except Exception as exc:  # noqa: BLE001 - one group's failure is not the run's
            logger.warning("could not read a proposal for %s: %s", vendor_id, exc)
            run.notes.append(f"{vendor_id}: {exc}")
            continue

        name = _normalize(proposal.name)
        if name in existing_names:
            # The correct outcome when the categorizer, not the taxonomy, was the
            # problem — and the reason the prompt invites it rather than forbidding
            # it. A model told never to name an existing category will invent one.
            run.already_present += 1
            continue
        if name in settled:
            run.dismissed_before += 1
            continue

        parent = by_name.get(_normalize(proposal.parent))
        session.add(SpendCategorySuggestion(
            spend_tree_id=company.spend_tree_id,
            company_id=company_id,
            parent_id=parent.id if parent else None,
            name=proposal.name.strip(),
            description=proposal.description.strip() or None,
            rationale=proposal.rationale.strip() or None,
            evidence_line_ids=[line.id for line in group],
            state=SuggestionState.PENDING,
        ))
        settled.add(name)
        run.proposed += 1
        logger.info("proposed %r under %r", proposal.name, proposal.parent)

    session.commit()
    return run
