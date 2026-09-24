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

from web_api.audit import LINE_AUDIT_FIELDS, LINE_VALUE_AUDIT_FIELDS, record_audit
from web_api.db.models import DocStatus, ErpEntry, Invoice, InvoiceLine, LineOrigin, LineStatus
from web_api.db.models.audit_log import SYSTEM_ACTOR
from web_api.fx import FxService
from web_api.fx.service import convert as fx_convert
from web_api.rollup import recompute_invoice_status

from .extractor import ExtractedLines

logger = logging.getLogger("ai_api.documents")

#: The audit action for a line removed so an extraction could take its place.
#: Distinct from an ordinary delete: it names *why* the line is gone.
REPLACED_ACTION = "superseded_by_extraction"

# Auditing the removal by diffing the line's values against nothing gives a
# `changes` list of everything it held. `description` and `amount` identify
# *which* line was removed; the rest of `LINE_VALUE_AUDIT_FIELDS` is there
# because a human may have corrected any of them, and this entry is the only
# place those corrections survive the replacement.
#
# `verified_fields` rides along for the same reason: which fields a person had
# settled is part of what was destroyed, and a bare list of values does not say
# whether anyone had looked at them.
_REMOVED_FIELDS = (
    *LINE_VALUE_AUDIT_FIELDS,
    "native_account_code",
    "origin",
    "verified_fields",
    *LINE_AUDIT_FIELDS,
)


def _name_and_description(item) -> tuple[str | None, str | None]:
    """Split one extracted line into the thing bought and the prose about it.

    The rule, in one tested place rather than in a prompt's good intentions:

    * Both stated, and different — keep both.
    * Only a description — **it is the name**. A document printing one text has
      named the item; filing that under `description` would leave the field
      every line is expected to carry empty on exactly the documents that read
      cleanly.
    * Both stated and identical — one text, said twice. Models echo, and storing
      the same string in both columns makes the split meaningless on the day it
      was introduced.
    * Neither — a line the model could not read. Null, never a guess, on the
      same rule that an unreadable amount becomes no amount.
    """
    name = (item.item_name or "").strip() or None
    description = (item.description or "").strip() or None
    if name is None:
        return description, None
    if description == name:
        return name, None
    return name, description


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _money(value, rate: Decimal | None) -> Decimal | None:
    """A money figure restated in the invoice's currency.

    A quantity is deliberately *not* passed through here: five of something is
    five of it whatever the money is worth.
    """
    amount = _dec(value)
    if amount is None or rate is None or rate == 1:
        return amount
    # `fx.convert` owns the rounding, so a converted line and a converted
    # invoice round the same way rather than drifting an øre apart.
    return fx_convert(amount, rate)


def replace_invoice_lines(
    session: Session,
    invoice: Invoice,
    extracted: ExtractedLines,
    *,
    fx: FxService,
    base_currency: str | None,
    rate: Decimal | None = None,
    document_total: Decimal | None = None,
    document_tax: Decimal | None = None,
    document_subtotal: Decimal | None = None,
) -> tuple[int, int]:
    """Replace the invoice's provisional lines with ``lines``. Does not commit.

    Returns ``(n_removed, n_written)``. The caller owns the transaction, so the
    removal, the insert, the audit rows and the rollup all land together or not
    at all — a half-applied replacement is an invoice that describes its spend
    twice.
    """
    lines = extracted.lines
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
        name, description = _name_and_description(item)
        row = InvoiceLine(
            company_id=invoice.company_id,
            invoice_id=invoice.id,
            # The order the document stated them in, which is how an invoice is
            # read. The row's random id would scramble it.
            sequence=seq,
            # Name and prose, split by one tested rule rather than by the
            # model's discipline — see `_name_and_description`.
            item_name=name,
            description=description,
            quantity=_dec(item.quantity),
            # What the quantity counts. Only the document reliably states this —
            # an ERP bill line carries a quantity and no unit at all — which is
            # most of the value of reading it.
            unit=(item.unit_type or "").strip() or None,
            # In the invoice's money, not the document's. Anthropic bills in
            # EUR against a DKK posting; writing the printed 90.00 into a DKK
            # column made a 672.83 invoice claim 90.00 of spend. `rate` is the
            # very one the reconciliation used, so the figure judged and the
            # figure written cannot disagree.
            unit_price=_money(item.unit_price, rate),
            amount=_money(item.amount, rate),
            # What the document printed about this line's tax. Money converts
            # with everything else; a *rate* is a percentage and does not.
            subtotal=_money(item.subtotal, rate),
            tax_amount=_money(item.tax_amount, rate),
            discount=_money(item.discount, rate),
            tax_rate=_dec(item.vat_rate),
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

    # Stored beside the as-posted number, never over it: `invoice_number` is
    # the evidence of what the ERP holds, and the two disagreeing is itself
    # information — the ERP's is a fallback identifier, or the scan belongs to
    # another invoice. Left null when the document stated none rather than
    # falling back to the posted value, which would make "read from the
    # document" indistinguishable from "copied from the ledger".
    invoice.document_invoice_number = extracted.invoice_number

    # The document's own arithmetic, beside the ledger's — which is not touched
    # here or anywhere else in extraction. When the two disagree the
    # disagreement *is* the information, and it is now visible rather than
    # being the grounds for throwing the reading away.
    #
    # Already in the invoice's currency, converted by the caller at the very
    # rate the reconciliation used, so the figure that was judged and the figure
    # stored can never disagree.
    invoice.document_total = document_total
    invoice.document_tax = document_tax
    invoice.document_subtotal = document_subtotal

    invoice.doc_status = DocStatus.PROCESSED
    invoice.doc_processed_at = datetime.now(timezone.utc)
    invoice.doc_error = None
    session.add(invoice)

    return len(removed_ids), len(lines)


def _audit_value(line: InvoiceLine, field: str):
    from web_api.audit import _norm

    return _norm(getattr(line, field, None))
