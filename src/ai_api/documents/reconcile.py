"""Does what the document said add up to what the ledger posted?

An extraction that misses a line is worse than no extraction at all: it would be
categorized, aggregated, and surfaced as a savings opportunity, and nothing
downstream could tell it was wrong. The invoice's own total is authoritative and
already in hand, so it is used as a checksum and a failing extraction is
rejected outright — the stand-in lines are a correct, if coarse, answer, and
keeping them beats replacing them with a confident wrong one.

Both the gross and the net-of-VAT figure are tried, because a document may state
its lines either way and there is no reliable signal which. ``ErpAccount.with_vat``
describes the *account*, not the document, so it cannot decide this.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from .. import config

_ZERO = Decimal("0")


class ReconcileResult(BaseModel):
    """The verdict, and enough of the arithmetic to explain it to a human."""

    ok: bool
    #: None when the invoice states no total — there was nothing to check
    #: against, so the extraction is judged only on whether it produced lines.
    checked: bool = True
    lines_total: Decimal | None = None
    gross_total: Decimal | None = None
    net_total: Decimal | None = None
    tolerance: Decimal | None = None
    reason: str | None = None

    model_config = {"arbitrary_types_allowed": True}


def tolerance_for(total: Decimal) -> Decimal:
    """How far the lines may be from the total.

    Relative and absolute, taking the larger. A percentage alone rejects a small
    invoice over a rounding øre; a fixed amount alone accepts a large invoice
    that is missing a whole line.
    """
    relative = abs(total) * Decimal(str(config.DOC_RECONCILE_TOLERANCE_PCT))
    absolute = Decimal(str(config.DOC_RECONCILE_TOLERANCE_ABS))
    return max(relative, absolute)


def reconcile(
    lines_total: Decimal, total: Decimal | None, tax: Decimal | None
) -> ReconcileResult:
    """Judge an extraction against the invoice's posted figures."""
    if total is None:
        return ReconcileResult(
            ok=True,
            checked=False,
            lines_total=lines_total,
            reason="the invoice states no total, so there is nothing to reconcile against",
        )

    gross = total
    net = total - (tax or _ZERO)
    tol = tolerance_for(total)
    ok = abs(lines_total - gross) <= tol or abs(lines_total - net) <= tol
    return ReconcileResult(
        ok=ok,
        lines_total=lines_total,
        gross_total=gross,
        net_total=net,
        tolerance=tol,
        reason=None
        if ok
        else (
            f"extracted lines sum to {lines_total}, which matches neither the "
            f"invoice total {gross} nor its net-of-VAT {net} within {tol}"
        ),
    )
