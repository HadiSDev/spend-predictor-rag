"""Do an invoice's lines add up to what its header states?

One rule, two callers, and that is the whole point of it living here:

* the **document extraction stage** (`ai_api/documents/`) uses it to accept or
  reject an extraction — lines that miss a line would be categorized,
  aggregated and surfaced as a savings opportunity with nothing downstream able
  to tell they were wrong;
* the **invoice payload** (`InvoiceDetailRead`) uses it to report a mismatch to
  a reviewer who is correcting lines by hand.

Two copies of the arithmetic would eventually disagree, and the visible symptom
would be an extraction accepted as reconciling that the reviewer is then told
does not reconcile. `ai_api` imports `web_api` and never the reverse, so the
domain is the only place both can reach.

Both the gross and the net-of-VAT figure are tried, because a document may state
its lines either way and there is no reliable signal which. ``ErpAccount.with_vat``
describes the *account*, not the document, so it cannot decide this.

The two callers differ in what they do with the verdict, not in how they reach
it: extraction **rejects** a mismatch, because a model producing lines that do
not add up has no reviewer standing behind them, while a human correction is
**warned** about and never blocked — a reviewer part-way through a multi-line
fix must not be blocked by their own unfinished work.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from . import config

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

    @property
    def delta(self) -> Decimal | None:
        """Signed distance from the nearest accepted total, or None when there
        is nothing to report.

        Signed so a reader can see *which way* it is out — "the lines are 200
        short" and "the lines are 200 over" call for different corrections.
        None when the lines reconcile, and None when the invoice states no total:
        an unknown total is not a mismatch.
        """
        if self.ok or self.lines_total is None or self.gross_total is None:
            return None
        candidates = [self.gross_total, self.net_total]
        nearest = min(
            (c for c in candidates if c is not None),
            key=lambda c: abs(self.lines_total - c),
        )
        return self.lines_total - nearest


def reconcile_lines(lines, invoice) -> ReconcileResult:
    """Judge an invoice's stored lines against its own header.

    The read-side entry point, taking the rows rather than a pre-computed sum so
    every caller sums them the same way. A null `amount` contributes nothing: it
    is an unstated figure, not a zero, and treating it as zero would report a
    shortfall the line never claimed.

    An invoice with **no lines** reconciles. There is nothing to check, and
    flagging every invoice whose lines have not been written yet would make the
    warning meaningless by the time a real mismatch appeared.
    """
    if not lines:
        return ReconcileResult(
            ok=True, checked=False, reason="the invoice has no lines to reconcile"
        )
    lines_total = sum((l.amount for l in lines if l.amount is not None), _ZERO)
    return reconcile(lines_total, invoice.total, invoice.tax)


def tolerance_for(total: Decimal) -> Decimal:
    """How far the lines may be from the total.

    Relative and absolute, taking the larger. A percentage alone rejects a small
    invoice over a rounding øre; a fixed amount alone accepts a large invoice
    that is missing a whole line.

    Read off the config module at call time, not captured at import, so a test
    that monkeypatches the tolerance affects both callers.
    """
    relative = abs(total) * Decimal(str(config.DOC_RECONCILE_TOLERANCE_PCT))
    absolute = Decimal(str(config.DOC_RECONCILE_TOLERANCE_ABS))
    return max(relative, absolute)


def reconcile(
    lines_total: Decimal, total: Decimal | None, tax: Decimal | None
) -> ReconcileResult:
    """Judge a set of lines against the invoice's posted figures."""
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
