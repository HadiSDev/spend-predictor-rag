"""Swap an invoice's provisional lines for the ones the document stated.

Whole-invoice, in one transaction. A partial replacement would leave the invoice
describing the same spend twice, and its total double-counted.

Three consequences are deliberate and each is load-bearing:

* **Postings are unlinked.** An extracted line has no ERP line identity, so the
  only way to relink a posting would be to match on amount or description — the
  guessing this codebase refuses everywhere else (`_source_line_id` in the sync
  runner *derives* its link, never matches it). A posting on an extracted invoice
  therefore shows no spend category. That is acceptable now precisely because the
  category has moved to where the reader is looking: the line.
* **Every removal is audited.** It is the only record that a human's verified
  category ever existed. Verification is a judgement made on this platform and
  there is not yet an affordance for a human to protect a line from replacement,
  so extraction wins and the audit row is what a future line-lock would be built
  on.
* **The rollup is recomputed.** An invoice whose verified lines are replaced by
  fresh uncategorized ones goes back to `uncategorized`; leaving it `verified`
  would assert a human judgement over lines no human has seen.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlmodel import Session, select

from web_api.audit import LINE_AUDIT_FIELDS, record_audit
from web_api.db.models import DocStatus, ErpEntry, Invoice, InvoiceLine, LineOrigin, LineStatus
from web_api.db.models.audit_log import SYSTEM_ACTOR
from web_api.fx import FxService
from web_api.rollup import recompute_invoice_status

from ..models import LineItem

logger = logging.getLogger("ai_api.documents")

#: The audit action for a line removed so an extraction could take its place.
#: Distinct from an ordinary delete: it names *why* the line is gone.
REPLACED_ACTION = "superseded_by_extraction"

# Auditing the removal by diffing the line's values against nothing gives a
# `changes` list of everything it held. `description` and `amount` are not in
# LINE_AUDIT_FIELDS (they are ERP-posted on an ordinary line and never edited),
# but they are exactly what identifies *which* line was removed.
_REMOVED_FIELDS = ("description", "amount", "native_account_code", "origin", *LINE_AUDIT_FIELDS)


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def replace_invoice_lines(
    session: Session,
    invoice: Invoice,
    lines: list[LineItem],
    *,
    fx: FxService,
    base_currency: str | None,
) -> tuple[int, int]:
    """Replace the invoice's provisional lines with ``lines``. Does not commit.

    Returns ``(n_removed, n_written)``. The caller owns the transaction, so the
    removal, the insert, the audit rows and the rollup all land together or not
    at all — a half-applied replacement is an invoice that describes its spend
    twice.
    """
    existing = list(
        session.exec(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice.id)
            .order_by(InvoiceLine.id)
        ).all()
    )
    removed_ids = [line.id for line in existing]

    if removed_ids:
        # Break the FK before deleting. A posting cannot point at an extracted
        # line — see the module docstring — so this is the honest end state, not
        # merely what the constraint requires.
        for entry in session.exec(
            select(ErpEntry).where(ErpEntry.source_invoice_line_id.in_(removed_ids))  # type: ignore[union-attr]
        ).all():
            entry.source_invoice_line_id = None
            session.add(entry)

    for line in existing:
        record_audit(
            session,
            entity_type="invoice_line",
            entity_id=line.id,
            action=REPLACED_ACTION,
            actor=SYSTEM_ACTOR,
            changes=[
                {"field": field, "old": _audit_value(line, field), "new": None}
                for field in _REMOVED_FIELDS
            ],
        )
        session.delete(line)

    for seq, item in enumerate(lines):
        row = InvoiceLine(
            company_id=invoice.company_id,
            invoice_id=invoice.id,
            # The order the document stated them in, which is how an invoice is
            # read. The row's random id would scramble it.
            sequence=seq,
            description=item.description,
            quantity=_dec(item.quantity),
            unit_price=_dec(item.unit_price),
            amount=_dec(item.amount),
            # Left uncategorized on purpose: the categorizer categorizes, on its
            # own schedule, exactly as it does for every other line.
            status=LineStatus.UNCATEGORIZED,
            origin=LineOrigin.DOCUMENT_AI,
        )
        session.add(row)
        # A line has no date of its own — it converts at its invoice's, so a
        # line and its invoice can never disagree on the rate used. A company
        # always has a base currency (required at creation), so None here is a
        # broken row, not a case to invent a rate for: the line stays
        # unconverted, which is visible, rather than converted at a substitute.
        if base_currency is not None:
            try:
                fx.convert_line(
                    row, base_currency,
                    currency=invoice.currency, invoice_date=invoice.invoice_date,
                )
            except Exception as exc:  # noqa: BLE001 - FX never fails an extraction
                logger.warning("  line conversion failed for invoice %s: %s", invoice.id, exc)

    session.flush()
    recompute_invoice_status(session, invoice.id)

    invoice.doc_status = DocStatus.PROCESSED
    invoice.doc_processed_at = datetime.now(timezone.utc)
    invoice.doc_error = None
    session.add(invoice)

    return len(removed_ids), len(lines)


def _audit_value(line: InvoiceLine, field: str):
    from web_api.audit import _norm

    return _norm(getattr(line, field, None))
