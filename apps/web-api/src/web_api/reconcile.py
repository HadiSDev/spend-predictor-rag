"""Do an invoice's lines add up to what its header states?"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from . import config

_ZERO = Decimal("0")


class ReconcileResult(BaseModel):
    """The verdict, and enough of the arithmetic to explain it to a human."""

    ok: bool
    checked: bool = True
    lines_total: Decimal | None = None
    gross_total: Decimal | None = None
    net_total: Decimal | None = None
    tolerance: Decimal | None = None
    reason: str | None = None
    totals_agree: bool | None = None
    document_total: Decimal | None = None

    model_config = {"arbitrary_types_allowed": True}

    @property
    def delta(self) -> Decimal | None:
        """Signed distance from the nearest accepted total, or None if nothing to report."""
        if self.ok or self.lines_total is None or self.gross_total is None:
            return None
        candidates = [self.gross_total, self.net_total]
        nearest = min(
            (c for c in candidates if c is not None),
            key=lambda c: abs(self.lines_total - c),
        )
        return self.lines_total - nearest


def reconcile_lines(lines, invoice) -> ReconcileResult:
    """Judge an invoice's stored lines against its own header."""
    if not lines:
        return ReconcileResult(
            ok=True, checked=False, reason="the invoice has no lines to reconcile"
        )
    lines_total = sum((l.amount for l in lines if l.amount is not None), _ZERO)
    return reconcile(
        lines_total,
        invoice.total,
        invoice.tax,
        document_total=getattr(invoice, "document_total", None),
        document_subtotal=getattr(invoice, "document_subtotal", None),
    )


def tolerance_for(total: Decimal) -> Decimal:
    """How far the lines may be from the total."""
    relative = abs(total) * Decimal(str(config.DOC_RECONCILE_TOLERANCE_PCT))
    absolute = Decimal(str(config.DOC_RECONCILE_TOLERANCE_ABS))
    return max(relative, absolute)


def internal_tolerance_for(total: Decimal) -> Decimal:
    """How far the lines may be from a total printed on the **same page**."""
    relative = abs(total) * Decimal(str(config.DOC_INTERNAL_TOLERANCE_PCT))
    absolute = Decimal(str(config.DOC_INTERNAL_TOLERANCE_ABS))
    return max(relative, absolute)


def _agrees(document_total: Decimal | None, document_subtotal: Decimal | None,
            total: Decimal | None, tax: Decimal | None) -> bool | None:
    """Do the document's figures and the ledger's describe the same invoice?"""
    if document_total is None or total is None:
        return None
    document = {document_total} | ({document_subtotal} if document_subtotal is not None else set())
    ledger = {total, total - (tax or _ZERO)}
    tol = tolerance_for(total)
    return any(abs(stated - posted) <= tol for stated in document for posted in ledger)


def totals_agree(invoice) -> bool | None:
    """Do the document's stated figures and the ledger's describe one invoice?"""
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
    """Judge a set of lines — against the document itself where we can."""
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
