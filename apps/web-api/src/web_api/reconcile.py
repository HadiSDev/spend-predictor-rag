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

**Two checks, because there are two questions.** The rule used to ask whether
*the document's lines* added up to *the ERP's total* — two systems, two VAT
conventions, one comparison — which conflated a question that has an exact
answer with one that does not:

1. **Did we read this document correctly?** Arithmetic within one source. If the
   lines do not sum to the total printed on the same page, we misread the page,
   and that is what rejection is for. Stricter than the old rule, not weaker.
2. **Do the supplier and the bookkeeper agree?** No exact answer. A German
   supplier printing gross and a Danish bookkeeper posting net are both correct;
   a partial posting, a credit note applied on one side and a typo are all real
   and all things a human resolves. This one **never rejects** — the verdict
   rides along as ``totals_agree`` for a reviewer to see.

The case that settled it: an Aquatuning invoice extracted to three correct
lines summing to 88,95 gross, with 15,90 of shipping stated only in its totals
block and a document total of 104,85, posted in Denmark as the net 83,88 with
``tax = 0.00``. Every figure right, the document internally exact, and the
extraction rejected — reported to the customer as a reading failure.

When the document states **no** total the previous rule stands unchanged: both
the gross and the net-of-VAT ledger figure are tried, because a document may
state its lines either way and there is no reliable signal which.
``ErpAccount.with_vat`` describes the *account*, not the document, so it cannot
decide this. A receipt often prints no totals block, and then the ledger's
figure is the only one there is.

The two callers still differ in what they do with the verdict, not in how they
reach it: extraction **rejects** a failed internal check, because a model
producing lines that do not add up to their own page has no reviewer standing
behind them, while a human correction is **warned** about and never blocked — a
reviewer part-way through a multi-line fix must not be blocked by their own
unfinished work.
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
    #: Did the *document's* stated total agree with the *ledger's*?
    #:
    #: A separate question from ``ok``, and separately answered: ``ok`` says
    #: whether we read the document correctly, this says whether the supplier
    #: and the bookkeeper agree. A disagreement never rejects — it is what a
    #: reviewer resolves, and rejecting means they never see the lines and
    #: cannot tell a misreading from a mis-posting.
    #:
    #: **None, not True**, when the document stated no total. "Nothing to
    #: compare" and "compared and agreed" are different claims, and a client
    #: that cannot tell them apart will present an unread document as a
    #: verified one.
    totals_agree: bool | None = None
    document_total: Decimal | None = None

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
    return reconcile(
        lines_total,
        invoice.total,
        invoice.tax,
        # What the document said about itself, when we read one. Null on an
        # invoice standing on ERP stand-in lines, which is the ordinary case and
        # falls straight through to the ledger comparison.
        document_total=getattr(invoice, "document_total", None),
        document_subtotal=getattr(invoice, "document_subtotal", None),
    )


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


def internal_tolerance_for(total: Decimal) -> Decimal:
    """How far the lines may be from a total printed on the **same page**.

    Tighter than :func:`tolerance_for`, which sizes a comparison between two
    systems. This one sizes arithmetic within one source, and a document is
    normally exact to the øre about itself. The absolute floor exists only
    because per-line rounding can drift a cent per line.
    """
    relative = abs(total) * Decimal(str(config.DOC_INTERNAL_TOLERANCE_PCT))
    absolute = Decimal(str(config.DOC_INTERNAL_TOLERANCE_ABS))
    return max(relative, absolute)


def _agrees(document_total: Decimal | None, document_subtotal: Decimal | None,
            total: Decimal | None, tax: Decimal | None) -> bool | None:
    """Do the document's figures and the ledger's describe the same invoice?

    ``None`` when either side states nothing.

    Both sides are offered gross **and** net, the same allowance the lines check
    already makes — a German supplier printing VAT-inclusive and a Danish
    bookkeeper posting VAT-exclusive are describing one invoice and agree
    completely. Reserving ``False`` for a real disagreement is the whole value
    of the flag; a flag that fires on every cross-border invoice is one a
    reviewer learns to ignore.
    """
    if document_total is None or total is None:
        return None
    document = {document_total} | ({document_subtotal} if document_subtotal is not None else set())
    ledger = {total, total - (tax or _ZERO)}
    tol = tolerance_for(total)
    return any(abs(stated - posted) <= tol for stated in document for posted in ledger)


def totals_agree(invoice) -> bool | None:
    """Do the document's stated figures and the ledger's describe one invoice?

    The read-side entry point, so a list row, an invoice detail and the
    extraction stage all reach the same answer through the same arithmetic.

    ``None`` when we read no document, or read one that stated no total —
    "nothing to compare" is not "compared and agreed", and a client that cannot
    tell them apart will present an unread document as a verified one.

    Computed, never stored, on the same reasoning as ``category_stale`` and
    ``needs_review``: the tolerance is a tunable judgement, and a stored verdict
    would be a snapshot of a setting that raising the setting would not move.
    """
    return _agrees(
        getattr(invoice, "document_total", None),
        getattr(invoice, "document_subtotal", None),
        invoice.total,
        invoice.tax,
    )


def reconcile(
    lines_total: Decimal,
    total: Decimal | None,
    tax: Decimal | None,
    *,
    document_total: Decimal | None = None,
    document_subtotal: Decimal | None = None,
) -> ReconcileResult:
    """Judge a set of lines — against the document itself where we can.

    **Two checks, because there are two questions.**

    When the document stated a total of its own, the lines are judged against
    *that*: arithmetic within one source, with an exact answer. Failing it means
    we misread the page, which is what rejection is for — and it is *stricter*
    than judging against the ledger, not weaker.

    The document's total is then compared with the ledger's, and that comparison
    never rejects. It has no exact answer: a partial posting, a credit note
    applied on one side and a plain typo are all real, and all things a human
    resolves. The verdict rides along as ``totals_agree``.

    When the document stated no total the previous rule stands unchanged — a
    receipt often prints no totals block, and then the ledger's figure is the
    only one there is.
    """
    stated = [f for f in (document_total, document_subtotal) if f is not None]
    if stated:
        reference = document_total if document_total is not None else stated[0]
        tol = internal_tolerance_for(reference)
        ok = any(abs(lines_total - figure) <= tol for figure in stated)
        printed = " nor ".join(str(f) for f in stated)
        return ReconcileResult(
            ok=ok,
            lines_total=lines_total,
            gross_total=total,
            net_total=None if total is None else total - (tax or _ZERO),
            tolerance=tol,
            totals_agree=_agrees(document_total, document_subtotal, total, tax),
            document_total=document_total,
            reason=None
            if ok
            else (
                f"extracted lines sum to {lines_total}, which does not match the "
                f"{printed} the document itself states, within {tol} — the "
                f"document was not read completely"
            ),
        )

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
