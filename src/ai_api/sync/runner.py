"""Sync runner — the batch pipeline for the ERP Procurement Agent.

Orchestrates the full end-to-end flow against any ``ErpConnector``:

    connect → fetch → persist → categorize → aggregate → detect → recommend

It replaces the per-invoice PDF flow with batch processing of structured
transaction data. Deterministic: a given seed/connector state yields the same
rows and the same summary on every run.

What gets synced is a database query, never an argument: every
``ErpIntegration`` that is still connected, using that integration's own stored
credentials. Companies and integrations are created through the customer API —
the runner never creates a tenant.

    python -m ai_api.sync.runner                       # every connected integration
    python -m ai_api.sync.runner --integration-id <id> # re-run just one
    python -m ai_api.sync.runner --since 2026-01-01    # backfill from a date
"""
from __future__ import annotations

import argparse
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, SQLModel, select

from ..aggregation import engine as aggregation
from web_api.connectors import get_connector
from web_api.connectors.base import (
    ErpAccountData,
    ErpConnector,
    ErpEntryData,
    ErpInvoiceData,
    ErpVendorData,
)
from web_api.db.models import (
    Company,
    DocStatus,
    ErpAccount,
    ErpEntry,
    ErpIntegration,
    File,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    LineOrigin,
    LineStatus,
    SpendCategory,
    SyncState,
    Vendor,
)
from web_api.db.models.enums import EXPENSE_ACCOUNT_TYPE
from ..persistence import LineGroundTruth
from ..procurement_agent import recommender
from ..redundancy import detector as redundancy
from web_api.audit import LINE_AUDIT_FIELDS, diff_changes, record_audit
from web_api.db.models.audit_log import SYSTEM_ACTOR
from web_api.db.session import engine
from web_api.fx import CONVERTED, UNCHANGED, UNCONVERTED, FxService
from web_api.integrations import connector_config as _connector_config
from web_api.rollup import recompute_invoice_status
from .categorizer import build_candidates, categorize

logger = logging.getLogger("ai_api.sync")

# Stable namespace so org/company/integration/entity IDs are reproducible across
# runs — re-syncing the same source is idempotent instead of duplicating rows.
_NS = uuid.UUID("5f4d6c3b-2a1e-4f8d-9c7b-0a1b2c3d4e5f")

_ZERO = Decimal("0")


def _det_id(*parts: str) -> str:
    return str(uuid.uuid5(_NS, ":".join(parts)))


def _dec(value) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


def _fx_counts() -> dict[str, int]:
    return {CONVERTED: 0, UNCONVERTED: 0, UNCHANGED: 0}


def _safe_convert(counts: dict[str, int], convert) -> None:
    """Convert one row, absorbing any failure into an unconverted count.

    Currency conversion is presentation; the ledger data is the point. A rate
    source that is down, slow, or returning nonsense must never cost us the
    entries we just fetched — so the row is persisted unconverted and the run
    goes on. A later recompute fills the gap in.
    """
    try:
        counts[convert()] += 1
    except Exception as exc:  # never let FX break persistence
        logger.warning("    FX: conversion failed, storing unconverted: %s", exc)
        counts[UNCONVERTED] += 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


# -- Work discovery ----------------------------------------------------------


def connected_integrations(
    session: Session, integration_id: str | None = None
) -> list[ErpIntegration]:
    """Every integration that should be synced.

    A connected integration *is* the statement "this company's ERP data is read
    from here" — it is what company creation and ``POST /erp-integrations``
    write, and what ``disconnect`` retracts. So that is the whole work list.

    Deliberately not filtered on ``Company.is_active``: a company is
    soft-deactivated for the customer-facing API, and whether that should also
    stop polling its ERP is a separate product question. Coupling the two here
    would decide it in the wrong place.

    ``integration_id`` only *narrows* what the database produced. It cannot name
    a tenant into existence — an id outside the connected set is an error, not
    something to create.
    """
    statement = select(ErpIntegration).where(ErpIntegration.disconnected_at.is_(None))
    if integration_id is not None:
        statement = statement.where(ErpIntegration.id == integration_id)
    rows = session.exec(statement.order_by(ErpIntegration.created_at, ErpIntegration.id)).all()
    if integration_id is not None and not rows:
        raise ValueError(
            f"No connected ERP integration with id {integration_id!r}. "
            "The runner only syncs integrations that already exist and are connected."
        )
    return list(rows)


def _resolve_since(state: SyncState, override: date | None) -> date | None:
    """Where this integration's fetch starts.

    An explicit override (a backfill) wins; otherwise the integration continues
    from its own watermark. A single value shared across integrations would be
    meaningless once one run covers several at different points in their
    history.
    """
    if override is not None:
        return override
    return state.last_invoice_date


# -- Persist -----------------------------------------------------------------


def _persist_accounts(
    session: Session, integration_id: str, accounts: list[ErpAccountData]
) -> dict[str, str]:
    """Upsert ERP accounts. Returns {erp_account_code: erp_account_id} for entry linking.

    Identity is `(erp_integration_id, erp_account_code)` — the natural key — and
    **not** a deterministic id looked up by primary key. It used to be the
    latter, which silently duplicated the whole chart:
    `POST /erp-integrations/{id}/refresh-accounts` writes these same rows with
    ordinary random ids, so `session.get(ErpAccount, deterministic_id)` never
    found them and inserted a second copy of every account. The pairs then
    drifted, because each writer only ever updated its own.

    Two writers share this table and only one rule may define identity. This is
    the rule the refresh endpoint already follows, so they now agree.
    """
    mapping: dict[str, str] = {}
    existing = {
        row.erp_account_code: row
        for row in session.exec(
            select(ErpAccount).where(ErpAccount.erp_integration_id == integration_id)
        ).all()
    }
    for acc in accounts:
        row = existing.get(acc.erp_account_code)
        if row is None:
            # New account: our sync selection defaults to enabled, and the ERP's
            # VAT value seeds the assumption. Existing rows keep whatever the
            # customer set — never reset from the ERP.
            row = ErpAccount(erp_integration_id=integration_id,
                             erp_account_code=acc.erp_account_code,
                             with_vat=acc.with_vat)
            session.add(row)
            # Not flushed: `id` has a client-side default so it is readable now,
            # and inserting here would precede the NOT NULL name set below.
            existing[acc.erp_account_code] = row
        # ERP-owned metadata only. `sync_enabled` and `with_vat` are the
        # customer's; this is the second writer that must respect that, and the
        # one whose clobbering would look like the setting resetting at random.
        row.erp_account_name = acc.erp_account_name
        row.erp_account_type = acc.erp_account_type
        row.parent_code = acc.parent_code
        row.is_active = acc.is_active
        row.raw_json = acc.raw
        mapping[acc.erp_account_code] = row.id
    session.commit()
    return mapping


def _enabled_account_codes(session: Session, integration_id: str) -> set[str]:
    """Return the native codes of accounts selected for sync (``sync_enabled``)."""
    rows = session.exec(
        select(ErpAccount).where(
            ErpAccount.erp_integration_id == integration_id,
            ErpAccount.sync_enabled == True,  # noqa: E712 - SQL boolean comparison
        )
    ).all()
    return {r.erp_account_code for r in rows}


def _vendor_key(v: ErpVendorData) -> str:
    """Global supplier identity: VAT number when present, else the normalized name.

    Vendors are a shared catalog (not company-scoped), so the same supplier seen
    by different companies/ERPs collapses onto one row.
    """
    vat = (v.vat_number or "").strip().lower()
    if vat:
        return f"vat:{vat}"
    return "name:" + " ".join((v.name or "").split()).lower()


def _persist_vendors(
    session: Session, vendors: list[ErpVendorData]
) -> dict[str, str]:
    """Upsert vendors into the global supplier catalog.

    Identity is VAT-else-name (``_vendor_key``); the returned map keys each ERP's
    own vendor id to our global vendor id so this sync's invoices can link.
    """
    mapping: dict[str, str] = {}
    for v in vendors:
        vendor_id = _det_id("vendor", _vendor_key(v))
        row = session.get(Vendor, vendor_id)
        if row is None:
            row = Vendor(id=vendor_id, name=v.name)
            session.add(row)
        row.name = v.name
        row.country_code = v.country_code
        row.vat_number = v.vat_number
        row.description = v.description
        mapping[v.erp_id] = vendor_id
    session.commit()
    return mapping


def _persist_file(
    session: Session, company_id: str, invoice_id: str, inv: ErpInvoiceData
) -> Optional[str]:
    """Upsert the scanned-document File for an invoice. Returns its id, or None.

    The invoice scan references the internal File domain via ``Invoice.file_id``.
    When the ERP voucher has no attached document, no File is created.
    """
    if not inv.file_name and not inv.file_ref:
        return None
    # Keyed on `file_ref` in preference to `file_name`: the ref is the ERP's own
    # identity for the document, while the name is a label a customer can change
    # — and a connector that starts reporting a name it previously left blank
    # would otherwise mint a second File row and orphan the first.
    file_id = _det_id("file", invoice_id, inv.file_ref or inv.file_name or "")
    row = session.get(File, file_id)
    if row is None:
        row = File(id=file_id, company_id=company_id, filename=inv.file_name or "scan.pdf",
                   file_type="invoice_pdf", storage_path=inv.file_ref or "")
        session.add(row)
    row.filename = inv.file_name or "scan.pdf"
    row.storage_path = inv.file_ref or ""
    row.status = "processed"
    return file_id


def _queue_document(row: Invoice, previous_file_id: Optional[str]) -> bool:
    """Set ``doc_status`` for an invoice the sync is writing. True if it queued it.

    The runner queues documents; it never processes them. Four cases, and the
    reasons matter:

    * **No document** — ``not_applicable``. Most vouchers have no scan and that
      is ordinary, not a failure; their stand-in lines are the answer.
    * **Currently processing** — left exactly as it is. A sync running alongside
      the stage must not yank an invoice out from under a run in flight.
    * **Already processed, same document** — stays ``processed``. Re-reading a
      document we have already read would replace good extracted lines with
      identical ones and reset their categorization for nothing. A *different*
      document is new evidence, so that returns to ``pending``.
    * **Already failed** — stays ``failed``. A sync is not a retry: the explicit
      path back is ``POST /invoices/{id}/reprocess``, and silently requeueing on
      every sync would both make that endpoint pointless and re-run a document
      that has already proved it cannot be read.
    """
    if row.file_id is None:
        row.doc_status = DocStatus.NOT_APPLICABLE
        return False
    if row.doc_status == DocStatus.PROCESSING:
        return False
    if row.doc_status == DocStatus.PROCESSED and row.file_id == previous_file_id:
        return False
    if row.doc_status == DocStatus.FAILED:
        return False
    row.doc_status = DocStatus.PENDING
    return True


def _persist_invoices(
    session: Session,
    company_id: str,
    invoices: list[ErpInvoiceData],
    vendor_map: dict[str, str],
    fx: FxService,
    base_currency: str,
    fx_counts: dict[str, int],
) -> tuple[dict[str, str], int, int, int]:
    """Upsert Invoice + InvoiceLine (+ scan File) as pending.

    The invoice is a purely internal scan: it references the File domain and is
    tied to entries via the voucher, but stores no ERP identity of its own (no
    ``erp_id``, no integration link — that provenance lives on the entries). The
    scan's ERP id is still used to derive a stable, deterministic invoice id so
    re-syncs upsert instead of duplicating.

    Returns ``(voucher_invoice_map, n_invoices, n_lines, n_queued)`` where the map
    ties each scan's voucher to its persisted invoice id, so entries can be linked
    without the invoice storing the voucher, and ``n_queued`` is how many invoices
    this run left waiting for document processing.
    """
    voucher_invoice_map: dict[str, str] = {}
    n_lines = 0
    n_queued = 0
    for inv in invoices:
        invoice_id = _det_id("invoice", company_id, inv.erp_id)
        vendor_id = vendor_map.get(inv.vendor_erp_id)
        file_id = _persist_file(session, company_id, invoice_id, inv)
        row = session.get(Invoice, invoice_id)
        if row is None:
            row = Invoice(id=invoice_id, company_id=company_id, status=InvoiceStatus.UNCATEGORIZED)
            session.add(row)
        previous_file_id = row.file_id
        row.vendor_id = vendor_id
        row.file_id = file_id
        if _queue_document(row, previous_file_id):
            n_queued += 1
        row.invoice_number = inv.invoice_number
        row.invoice_date = inv.invoice_date
        row.currency = inv.currency
        row.total = _dec(inv.total)
        row.tax = _dec(inv.tax)
        # Status is a rollup of the lines; not reset on re-sync.
        row.raw_json = inv.raw
        # Converted at the invoice's own date, never today's. `currency`,
        # `total` and `tax` above stay exactly as the ERP posted them.
        _safe_convert(fx_counts, lambda: fx.convert_invoice(row, base_currency))

        if inv.voucher_id is not None:
            voucher_invoice_map[inv.voucher_id] = invoice_id

        for idx, line in enumerate(inv.lines):
            line_key = line.line_erp_id or str(idx)
            line_id = _det_id("line", invoice_id, line_key)
            lrow = session.get(InvoiceLine, line_id)
            if lrow is None:
                lrow = InvoiceLine(id=line_id, company_id=company_id,
                                   invoice_id=invoice_id, status=LineStatus.UNCATEGORIZED,
                                   origin=LineOrigin.ERP)
                session.add(lrow)
            lrow.origin = LineOrigin.ERP
            # The ERP stated the lines in this order; an invoice reads top to
            # bottom, and the row's random id would scramble it.
            lrow.sequence = idx
            lrow.description = line.description
            lrow.quantity = _dec(line.quantity)
            lrow.unit = line.unit
            lrow.unit_price = _dec(line.unit_price)
            lrow.amount = _dec(line.amount)
            lrow.native_account_code = line.native_account_code
            # Status is NOT reset on re-sync: an already-categorized or verified
            # line keeps its lifecycle state (verified results are preserved).
            lrow.raw_json = line.raw
            # A line has no date or currency of its own — it converts at its
            # invoice's, so a line and its invoice can never disagree on rate.
            _safe_convert(
                fx_counts,
                lambda lrow=lrow: fx.convert_line(
                    lrow, base_currency,
                    currency=inv.currency, invoice_date=inv.invoice_date,
                ),
            )
            n_lines += 1
    session.commit()
    return voucher_invoice_map, len(invoices), n_lines, n_queued


def _source_line_id(
    session: Session, source_invoice_id: Optional[str], entry: ErpEntryData
) -> Optional[str]:
    """The `InvoiceLine` a posting came from, or None when it came from no line.

    None is the ordinary case, not a failure: input VAT, the payable
    counterparty and journal entries are properties of a whole voucher. It is
    also what we fall back to when the connector names a line the invoice scan
    did not deliver — a dangling FK would abort the whole sync over one posting.
    """
    if source_invoice_id is None or entry.source_line_erp_id is None:
        return None
    line_id = _det_id("line", source_invoice_id, entry.source_line_erp_id)
    if session.get(InvoiceLine, line_id) is None:
        logger.warning("  entry %s references unknown invoice line %s",
                       entry.erp_entry_id, entry.source_line_erp_id)
        return None
    return line_id


def _persist_entries(
    session: Session,
    company_id: str,
    integration_id: str,
    entries: list[ErpEntryData],
    voucher_invoice_map: dict[str, str],
    account_map: dict[str, str],
    fx: FxService,
    base_currency: str,
    fx_counts: dict[str, int],
) -> tuple[int, int]:
    """Upsert raw ErpEntry rows, linking each to its invoice via the voucher.

    Entries are stored as raw financial context and are NOT categorized. An
    entry's ``source_invoice_id`` is set from ``voucher_invoice_map`` when its
    voucher has an invoice scan; otherwise it stays NULL (payments, journals).
    Returns ``(n_entries, n_linked)``. Entries whose account is unknown to the
    persisted chart of accounts are skipped (the FK requires a known account).

    When the connector says which invoice line a posting came from, the entry is
    also linked to that ``InvoiceLine`` — many entries to one line, since a line
    may be posted across several accounts. The line id is *derived*, not looked
    up by matching: ``_persist_invoices`` builds it from the same
    ``(invoice_id, line_erp_id)`` pair, so the two agree by construction. The
    row is still confirmed to exist before the FK is set, because a connector is
    free to reference a line its invoice scan never delivered.
    """
    n_entries = 0
    n_linked = 0
    for e in entries:
        erp_account_id = account_map.get(e.erp_account_code)
        if erp_account_id is None:
            logger.warning("  skipping entry %s: unknown account %s",
                           e.erp_entry_id, e.erp_account_code)
            continue
        entry_id = _det_id("entry", integration_id, e.erp_entry_id)
        source_invoice_id = voucher_invoice_map.get(e.voucher_id)
        source_invoice_line_id = _source_line_id(session, source_invoice_id, e)
        row = session.get(ErpEntry, entry_id)
        if row is None:
            # The entry id is still derived from integration_id (deterministic,
            # idempotent), but the integration is no longer stored on the row —
            # it is reached through the account.
            row = ErpEntry(id=entry_id, company_id=company_id,
                           erp_account_id=erp_account_id,
                           entry_type=e.entry_type)
            session.add(row)
        row.erp_account_id = erp_account_id
        row.entry_type = e.entry_type
        row.voucher_id = e.voucher_id
        row.source_invoice_id = source_invoice_id
        row.source_invoice_line_id = source_invoice_line_id
        row.accounting_date = e.accounting_date
        row.description = e.description
        row.debit_amount = _dec(e.debit_amount)
        row.credit_amount = _dec(e.credit_amount)
        row.currency = e.currency
        row.erp_entry_id = e.erp_entry_id
        row.raw_json = e.raw
        # Converted at the posting's accounting date. Debit and credit are each
        # converted from their own posted value, never derived from one another.
        _safe_convert(fx_counts, lambda row=row: fx.convert_entry(row, base_currency))
        n_entries += 1
        if source_invoice_id is not None:
            n_linked += 1
    session.commit()
    return n_entries, n_linked


def _persist_standin_lines(
    session: Session,
    company_id: str,
    invoice_ids: set[str],
    fx: FxService,
    base_currency: str,
    fx_counts: dict[str, int],
) -> int:
    """Stand a line in for every expense posting on an invoice that has none.

    The invoice line is the unit of spend this product works in — it is what
    carries a description, a category and a human's verification. When no better
    source has produced one (no document extraction has succeeded, and the ERP
    supplied no bill lines), each **expense** posting stands in for one, so
    categorization and the reports are never dark on a voucher just because it
    arrived without a scan.

    Only expense postings. Input VAT, the payable, bank and the rest are not
    spend, and a line for each of them would make an invoice's lines sum to
    zero. `EXPENSE_ACCOUNT_TYPE` is the *same* constant the voucher's Total
    Spend is computed from, which is what keeps the lines and the figure above
    them counting the same postings.

    Never runs where the invoice already has lines: an invoice holds exactly one
    origin at a time, so `document_ai` lines are safe from a later sync and ERP
    lines are not doubled by stand-ins for the same money.

    Returns the number of stand-in lines written.
    """
    if not invoice_ids:
        return 0

    # One query for the whole batch: the postings of these invoices, with their
    # account's type and code alongside.
    rows = session.exec(
        select(ErpEntry, ErpAccount.erp_account_type, ErpAccount.erp_account_code)
        .join(ErpAccount, ErpAccount.id == ErpEntry.erp_account_id)
        .where(ErpEntry.source_invoice_id.in_(invoice_ids))  # type: ignore[union-attr]
    ).all()

    postings: dict[str, list[tuple[ErpEntry, str]]] = {}
    for entry, account_type, account_code in rows:
        if account_type != EXPENSE_ACCOUNT_TYPE:
            continue
        postings.setdefault(entry.source_invoice_id, []).append((entry, account_code))

    n_written = 0
    for invoice_id in sorted(invoice_ids):
        existing = session.exec(
            select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id)
        ).all()
        # Any line from a better source wins, and a re-sync must find its own
        # stand-ins rather than skip them — otherwise a posting added to an
        # existing voucher would never get a line.
        if any(line.origin != LineOrigin.ENTRY_FALLBACK for line in existing):
            continue

        invoice = session.get(Invoice, invoice_id)
        if invoice is None:  # pragma: no cover - the map only holds persisted ids
            continue

        for seq, (entry, account_code) in enumerate(
            sorted(postings.get(invoice_id, []), key=lambda pair: pair[0].id)
        ):
            # Keyed off the posting it stands for, so a re-sync upserts the same
            # row instead of minting a second line for the same money.
            line_id = _det_id("standin", entry.id)
            lrow = session.get(InvoiceLine, line_id)
            if lrow is None:
                lrow = InvoiceLine(id=line_id, company_id=company_id,
                                   invoice_id=invoice_id, status=LineStatus.UNCATEGORIZED,
                                   origin=LineOrigin.ENTRY_FALLBACK)
                session.add(lrow)
            lrow.origin = LineOrigin.ENTRY_FALLBACK
            # Stand-ins have no document order to preserve, so they take the
            # posting order — stable across re-syncs, which is what matters.
            lrow.sequence = seq
            # Signed, exactly as `_net_spend` reads a posting: a credit on an
            # expense account is a refund and the line is negative.
            lrow.amount = (entry.debit_amount or _ZERO) - (entry.credit_amount or _ZERO)
            lrow.description = entry.description
            lrow.native_account_code = account_code
            # Status is not reset: a re-sync must not undo a categorization.
            _safe_convert(
                fx_counts,
                lambda lrow=lrow, entry=entry, invoice=invoice: fx.convert_line(
                    lrow, base_currency,
                    currency=entry.currency or invoice.currency,
                    invoice_date=invoice.invoice_date,
                ),
            )
            # The posting and the line it produced point at each other, so the
            # existing entry→line link keeps resolving and a posting still shows
            # its own category.
            entry.source_invoice_line_id = line_id
            n_written += 1

    session.commit()
    return n_written


# -- Categorize --------------------------------------------------------------


def _spend_category_map(session: Session, company_id: str) -> dict[tuple, str]:
    """Map ``(level_2, level_3) -> spend_category_id`` for a company's spend tree.

    A spend-tree node is identified by its position in the taxonomy (its levels),
    not by an ERP account code — that lives on ``ErpAccount``. Empty until a
    company's ``SpendCategory`` rows are seeded; used to resolve the accepted
    assignment on the domain line when a categorizer match lands on a real node.
    """
    rows = session.exec(
        select(SpendCategory).where(SpendCategory.company_id == company_id)
    ).all()
    return {(r.level_2, r.level_3): r.id for r in rows}


def _categorize_pending(
    session: Session, integration_id: str, company_id: str, candidates: list
) -> dict[str, int]:
    """Categorize every uncategorized line for the integration.

    The result is written directly onto the domain ``InvoiceLine`` (level
    snapshot, account, confidence, rationale, plus ``spend_category_id`` when the
    match resolves to a real seeded ``SpendCategory``) and the line's status moves
    to ``ai_categorized`` or ``ai_failed``. Each categorized line also gets an
    ``AuditLog`` row attributed to ``system`` and a synthetic ground-truth row in
    the ai_api-owned ``line_ground_truth`` store. A ``verified`` line is left
    untouched — human review is authoritative and is not overwritten by a re-run.
    The invoice status is then recomputed as a rollup of its lines.

    The invoice carries no integration link, so its scope is reached through the
    entries: an invoice belongs to this integration iff one of the integration's
    entries references it via ``source_invoice_id``.
    """
    invoice_ids = [
        iid for iid in session.exec(
            select(ErpEntry.source_invoice_id)
            .join(ErpAccount, ErpEntry.erp_account_id == ErpAccount.id)
            .where(
                ErpAccount.erp_integration_id == integration_id,
                ErpEntry.source_invoice_id.is_not(None),
            )
            .distinct()
        ).all()
    ]
    invoices = session.exec(
        select(Invoice).where(Invoice.id.in_(invoice_ids))
    ).all() if invoice_ids else []

    category_map = _spend_category_map(session, company_id)

    stats = {"categorized": 0, "failed": 0, "invoices_completed": 0, "invoices_failed": 0}
    for inv in invoices:
        lines = session.exec(
            select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)
        ).all()
        # Only uncategorized lines are processed; verified (and already
        # AI-categorized) lines are not overwritten unless explicitly re-triggered.
        pending = [ln for ln in lines if ln.status == LineStatus.UNCATEGORIZED]
        if not pending:
            continue

        any_failed = False
        for ln in pending:
            match = categorize(ln.description or "", ln.native_account_code, candidates)

            before = {f: getattr(ln, f) for f in LINE_AUDIT_FIELDS}

            # Synthetic ground truth lives only in the ai_api store, never on the
            # domain line.
            gt = session.exec(
                select(LineGroundTruth).where(
                    LineGroundTruth.invoice_line_id == ln.id
                )
            ).first()
            if gt is None:
                gt = LineGroundTruth(invoice_line_id=ln.id)
                session.add(gt)
            gt.gt_level_1 = match.gt_level_1
            gt.gt_level_2 = match.gt_level_2
            gt.gt_level_3 = match.gt_level_3
            gt.gt_account_code = match.gt_account_code

            if match.matched:
                # The result is written onto the line. spend_category_id is set
                # only when the match resolves to a real seeded category.
                ln.level_1 = match.level_1
                ln.level_2 = match.level_2
                ln.level_3 = match.level_3
                ln.account_code = match.account_code
                ln.account_name = match.account_name
                ln.confidence = _dec(match.confidence)
                ln.rationale = match.rationale
                ln.spend_category_id = category_map.get((match.level_2, match.level_3))
                ln.status = LineStatus.AI_CATEGORIZED
                ln.error_message = None
                stats["categorized"] += 1
            else:
                ln.rationale = match.rationale
                ln.status = LineStatus.AI_FAILED
                ln.error_message = match.rationale
                any_failed = True
                stats["failed"] += 1
            session.add(ln)

            after = {f: getattr(ln, f) for f in LINE_AUDIT_FIELDS}
            record_audit(
                session,
                entity_type="invoice_line",
                entity_id=ln.id,
                action="ai_categorize",
                actor=SYSTEM_ACTOR,
                changes=diff_changes(before, after, LINE_AUDIT_FIELDS),
            )

        # Invoice status is a rollup of its lines, recomputed in this transaction.
        recompute_invoice_status(session, inv.id)
        if any_failed:
            stats["invoices_failed"] += 1
        else:
            stats["invoices_completed"] += 1
    session.commit()
    return stats


# -- Downstream stubs (aggregate / detect / recommend) -----------------------


def _call_stub(label: str, fn, *args) -> object:
    """Call a downstream stub, tolerating not-yet-implemented bodies.

    The aggregation/redundancy/recommender modules are separate workstreams.
    The runner wires the calls now; a stub that returns ``...`` (an unimplemented
    body) or raises ``NotImplementedError`` is reported as 'stub', not a failure.
    """
    try:
        result = fn(*args)
    except NotImplementedError:
        logger.info("  %s: not implemented yet (stub)", label)
        return "stub"
    if result is Ellipsis or result is None:
        logger.info("  %s: stub (no output yet)", label)
        return "stub"
    logger.info("  %s: %s rows", label, len(result) if hasattr(result, "__len__") else "ok")
    return result


# -- Summary -----------------------------------------------------------------


def _build_summary(session: Session, company_id: str) -> dict:
    invoices = session.exec(select(Invoice).where(Invoice.company_id == company_id)).all()
    lines = session.exec(select(InvoiceLine).where(InvoiceLine.company_id == company_id)).all()
    entries = session.exec(select(ErpEntry).where(ErpEntry.company_id == company_id)).all()
    # Vendors are a global catalog; count the distinct suppliers this company's
    # invoices reference rather than a (now non-existent) company scope.
    vendor_ids = {inv.vendor_id for inv in invoices if inv.vendor_id is not None}

    def _counts(rows, attr="status"):
        out: dict[str, int] = {}
        for r in rows:
            out[getattr(r, attr)] = out.get(getattr(r, attr), 0) + 1
        return out

    categorized = [ln for ln in lines if ln.status in (LineStatus.AI_CATEGORIZED, LineStatus.VERIFIED)]
    total_spend = sum((ln.amount or Decimal(0)) for ln in categorized)
    # The predicted level snapshot lives on the line itself now.
    spend_by_l2: dict[str, Decimal] = {}
    for ln in categorized:
        key = ln.level_2 or "Uncategorized"
        spend_by_l2[key] = spend_by_l2.get(key, Decimal(0)) + (ln.amount or Decimal(0))

    return {
        "vendors": len(vendor_ids),
        "invoices": len(invoices),
        "invoice_status": _counts(invoices),
        "lines": len(lines),
        "line_status": _counts(lines),
        "entries": len(entries),
        "entries_linked": sum(1 for e in entries if e.source_invoice_id is not None),
        "categorized_spend": float(total_spend),
        "spend_by_level_2": {k: float(v) for k, v in sorted(spend_by_l2.items())},
    }


# -- Public API --------------------------------------------------------------


def _sync_one(
    session: Session,
    integration: ErpIntegration,
    connector: ErpConnector,
    since_override: date | None,
    fx: FxService,
    base_currency: str,
) -> dict:
    """Run the full pipeline for one integration.

    Unchanged from the single-tenant version except for where its ids come from:
    ``company_id`` and ``integration_id`` are read off the integration row
    instead of being invented.

    ``base_currency`` likewise comes off the company row. The runner reads it
    and never writes it: it is a customer setting, like ``sync_enabled``.
    """
    company_id = integration.company_id
    integration_id = integration.id
    fx_counts = _fx_counts()

    sync_state = _begin_sync_state(session, integration_id)
    since = _resolve_since(sync_state, since_override)

    try:
        # Reaching the ERP is this integration's problem, not the run's — one
        # unreachable system must not stop every other tenant.
        connector.authorize()
        if not connector.test_connection():
            raise RuntimeError(
                f"Could not reach the {integration.erp_type} ERP — is it running?"
            )

        # 1. Fetch accounts + vendors, and persist accounts first so the sync
        #    selection (sync_enabled) is known before pulling entries.
        logger.info("  [1/6] Fetching accounts & vendors…")
        accounts = connector.fetch_accounts()
        vendors = connector.fetch_vendors(since=since)
        account_map = _persist_accounts(session, integration_id, accounts)
        enabled_codes = _enabled_account_codes(session, integration_id)
        logger.info("    fetched %d accounts (%d enabled for sync), %d vendors",
                    len(accounts), len(enabled_codes), len(vendors))

        # Entries are the primary ledger unit, but only for the accounts we
        # selected (fetch-time gate — we don't pull the whole ERP). Invoice
        # scans are then pulled per voucher for the invoice-bearing vouchers.
        entries = connector.fetch_entries(since=since, account_codes=enabled_codes)
        vouchers: dict[str, list[ErpEntryData]] = {}
        for e in entries:
            vouchers.setdefault(e.voucher_id, []).append(e)
        invoice_vouchers = [
            v for v, es in vouchers.items()
            if any(e.entry_type == "purchase_invoice" for e in es)
        ]
        invoices: list[ErpInvoiceData] = []
        for v in invoice_vouchers:
            scan = connector.fetch_invoice_scan(v)
            if scan is not None:
                invoices.append(scan)
        logger.info("    fetched %d entries (%d vouchers, %d invoice scans)",
                    len(entries), len(vouchers), len(invoices))

        # 2. Persist
        logger.info("  [2/6] Persisting to PostgreSQL…")
        vendor_map = _persist_vendors(session, vendors)
        voucher_invoice_map, n_inv, n_lines, n_queued = _persist_invoices(
            session, company_id, invoices, vendor_map, fx, base_currency, fx_counts
        )
        n_entries, n_linked = _persist_entries(
            session, company_id, integration_id, entries,
            voucher_invoice_map, account_map, fx, base_currency, fx_counts
        )
        # After the entries, because a stand-in line stands in for a *posting* —
        # there is nothing to stand in for until they are persisted.
        n_standin = _persist_standin_lines(
            session, company_id, set(voucher_invoice_map.values()),
            fx, base_currency, fx_counts,
        )
        n_lines += n_standin
        logger.info("    persisted %d invoices, %d lines (%d standing in for a posting), "
                    "%d entries (%d linked to an invoice)",
                    n_inv, n_lines, n_standin, n_entries, n_linked)
        logger.info("    queued %d invoices for document processing", n_queued)
        logger.info("    converted to %s: %d rows (%d unconverted, %d already current)",
                    base_currency, fx_counts[CONVERTED],
                    fx_counts[UNCONVERTED], fx_counts[UNCHANGED])

        # 3. Categorize
        logger.info("  [3/6] Categorizing pending invoice lines…")
        candidates = build_candidates(accounts)
        cat_stats = _categorize_pending(session, integration_id, company_id, candidates)
        logger.info("    categorized=%d failed=%d (invoices: %d completed, %d failed)",
                    cat_stats["categorized"], cat_stats["failed"],
                    cat_stats["invoices_completed"], cat_stats["invoices_failed"])

        # 4/5/6. Downstream (separate workstreams — wired as stubs for now)
        logger.info("  [4/6] Aggregating spend…")
        _call_stub("spend_by_category", aggregation.spend_by_category, company_id)
        _call_stub("spend_by_vendor", aggregation.spend_by_vendor, company_id)
        logger.info("  [5/6] Detecting redundant vendors…")
        _call_stub("same_category_overlaps", redundancy.find_same_category_overlaps, company_id)
        logger.info("  [6/6] Generating savings recommendations…")
        _call_stub("recommendations", recommender.all_recommendations, company_id)

        summary = _build_summary(session, company_id)
        _finish_sync_state(session, sync_state, invoices, status="idle")
        summary["status"] = "ok"
        summary["company_id"] = company_id
        summary["erp_type"] = integration.erp_type
        summary["categorization"] = cat_stats
        summary["accounts"] = len(accounts)
        summary["accounts_enabled"] = len(enabled_codes)
        # The backlog the document stage will face, visible without querying the
        # database.
        summary["documents_queued"] = n_queued
        summary["standin_lines"] = n_standin
        summary["base_currency"] = base_currency
        summary["fx"] = fx_counts
        return summary
    except Exception as exc:
        # The watermark is left where it was: a failed run has not advanced.
        _finish_sync_state(session, sync_state, [], status="error", error=str(exc))
        raise


def run_sync(*, since: date | None = None, integration_id: str | None = None) -> dict[str, dict]:
    """Sync every connected ERP integration. Returns one summary per integration.

    Takes no tenant and no credentials: the work list is
    ``connected_integrations()`` and each connector is built from that
    integration's own stored credential. A failure is confined to the
    integration it happened to — the rest of the run continues.
    """
    SQLModel.metadata.create_all(engine)
    results: dict[str, dict] = {}

    with Session(engine) as session:
        work = connected_integrations(session, integration_id)
        if not work:
            logger.info(
                "No connected ERP integrations — create a company with an ERP "
                "connection in Settings first."
            )
            return results

        logger.info("Syncing %d connected integration(s)…", len(work))
        # One FX service for the whole run: its memo means a date shared by two
        # integrations costs one rate lookup, not two.
        fx = FxService(session)
        for integration in work:
            company = session.get(Company, integration.company_id)
            label = company.name if company is not None else integration.company_id
            base_currency = company.base_currency if company is not None else "EUR"
            logger.info("[%s] %s via %s", label, integration.id, integration.erp_type)
            try:
                config = _connector_config(session, integration)
                connector: ErpConnector = get_connector(integration.erp_type, config)
                results[integration.id] = _sync_one(
                    session, integration, connector, since, fx, base_currency
                )
                logger.info("  done: %s", results[integration.id])
            except Exception as exc:
                # Isolated on purpose: tenant B is not punished for tenant A's
                # ERP being down, a stale key, or an unregistered connector.
                logger.error("  FAILED: %s", exc)
                results[integration.id] = {
                    "status": "error",
                    "error": str(exc),
                    "company_id": integration.company_id,
                    "erp_type": integration.erp_type,
                }
    return results


# -- SyncState helpers -------------------------------------------------------


def _begin_sync_state(session: Session, integration_id: str) -> SyncState:
    """Mark this integration as syncing, preserving what it already knows.

    Loaded and updated rather than merged from a fresh object: a fresh
    ``SyncState`` carries ``last_invoice_date = None``, so merging one would
    erase the watermark this run is about to read.
    """
    state_id = _det_id("sync_state", integration_id)
    state = session.get(SyncState, state_id)
    if state is None:
        state = SyncState(id=state_id, erp_integration_id=integration_id)
        session.add(state)
    state.status = "syncing"
    state.error_message = None
    session.commit()
    return state


def _finish_sync_state(
    session: Session,
    state: SyncState,
    invoices: list[ErpInvoiceData],
    *,
    status: str,
    error: str | None = None,
) -> None:
    watermark = max((inv.invoice_date for inv in invoices), default=None)
    state.last_sync_at = _now()
    # Only ever moved forward, and never by a failed run — a sync that raised
    # has not covered the period it was reaching for, so the next run must
    # still start where the last successful one stopped.
    if watermark is not None and (
        state.last_invoice_date is None or watermark > state.last_invoice_date
    ):
        state.last_invoice_date = watermark
    state.status = status
    state.error_message = error
    session.add(state)
    session.commit()


# -- CLI ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync every connected ERP integration. Companies and their "
                    "ERP connections are created in the app, never here.",
    )
    parser.add_argument(
        "--integration-id", default=None,
        help="Sync only this integration (must already exist and be connected)",
    )
    parser.add_argument(
        "--since", default=None,
        help="Backfill from this ISO date, overriding each integration's own watermark",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    since = date.fromisoformat(args.since) if args.since else None

    try:
        results = run_sync(since=since, integration_id=args.integration_id)
    except ValueError as exc:  # unknown --integration-id
        parser.error(str(exc))
        return 2

    if not results:
        print("\nNothing to sync — no connected ERP integrations.")
        return 0

    failed = 0
    for integration_id, summary in results.items():
        print(f"\n=== {integration_id} ({summary.get('erp_type')}) ===")
        if summary.get("status") == "error":
            failed += 1
            print(f"status: error\nerror: {summary['error']}")
            continue
        for key, value in summary.items():
            print(f"{key}: {value}")

    # A scheduler still needs to see that something broke, even though the
    # other integrations were synced.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
