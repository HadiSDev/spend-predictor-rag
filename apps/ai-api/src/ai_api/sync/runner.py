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
    python -m ai_api.sync.runner --hard-reset          # let the ERP win over verified fields

A field a human has verified is never overwritten by an ordinary run; the ERP
restates everything else. ``--hard-reset`` is the one, explicit way back.
"""
from __future__ import annotations

import argparse
import logging
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlmodel import Session, SQLModel, select

from .. import config as ai_config
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
from ..persistence import CategorizationCache, LineGroundTruth
from ..procurement_agent import recommender
from ..redundancy import detector as redundancy
from web_api.audit import (
    LINE_AUDIT_FIELDS,
    LINE_VALUE_AUDIT_FIELDS,
    diff_changes,
    record_audit,
)
from web_api.db.models.audit_log import SYSTEM_ACTOR
from web_api.db.session import engine
from web_api.fx import CONVERTED, UNCHANGED, UNCONVERTED, FxService
from web_api.integrations import connector_config as _connector_config
from web_api.rollup import recompute_invoice_status
from web_api.verified import clear_verified, is_verified
from .cache import question_key, question_sample, tree_hash
from .categorizer import (
    CategoryMatch,
    build_candidates_from_retrieval,
    build_candidates_from_tree,
)
from .llm_categorizer import CategorizerUnavailable, LineContext, categorize_line

logger = logging.getLogger("ai_api.sync")

# Stable namespace so org/company/integration/entity IDs are reproducible across
# runs — re-syncing the same source is idempotent instead of duplicating rows.
_NS = uuid.UUID("5f4d6c3b-2a1e-4f8d-9c7b-0a1b2c3d4e5f")

_ZERO = Decimal("0")

#: The audit action for a line the ERP has stopped stating. Distinct from
#: `superseded_by_extraction`: nothing replaced this line's *content* — the
#: ledger simply no longer carries the line it was built from.
WITHDRAWN_ACTION = "withdrawn_by_erp"

#: The audit action for a posting removed because its voucher was voided.
#: Distinct from `withdrawn_by_erp`: that line was restated differently, this
#: whole transaction was undone.
VOIDED_ACTION = "voucher_voided_in_erp"

#: What a withdrawn posting held, for the audit row that is now its only record.
_VOIDED_ENTRY_FIELDS = (
    "voucher_id", "entry_type", "accounting_date", "description",
    "debit_amount", "credit_amount", "currency", "erp_entry_id",
    "source_invoice_id", "source_invoice_line_id",
)

# Auditing a removal by diffing the line against nothing yields everything it
# held, which is the only record it ever existed. Mirrors
# `documents/replace.py::_REMOVED_FIELDS` and for the same reason: `item_name`
# and `amount` say *which* line went, `verified_fields` says whether anyone had
# settled any of it, and the categorization is what a human may have supplied.
#
# Splatted from `LINE_VALUE_AUDIT_FIELDS` rather than hand-listed. It was
# hand-listed, and the copy is exactly how a correctable field goes unrecorded:
# adding one to the audit set reached `_REMOVED_FIELDS`, which splats, and
# silently missed this one, which did not — so the same line withdrawn by a sync
# lost the value that an extraction would have preserved.
_WITHDRAWN_FIELDS = (
    *LINE_VALUE_AUDIT_FIELDS,
    "native_account_code", "origin", "sequence", "verified_fields",
    *LINE_AUDIT_FIELDS,
)

#: `Vendor.description_source` values the sync must respect. `web` is the
#: enrichment stage's. Named here rather than imported from
#: `ai_api.enrichment.vendors`, because a sync must not depend on a stage that
#: may never have been enabled.
_HUMAN_DESCRIPTION = "human"
_ERP_DESCRIPTION = "erp"

#: How many nodes retrieval fetches before sibling expansion. Small on purpose:
#: the expansion is what widens the shortlist, and a large `top_k` on a broad
#: tree pulls in whole branches that have nothing to do with the line.
CATEGORY_RETRIEVAL_TOP_K = int(os.getenv("CATEGORY_RETRIEVAL_TOP_K", "5"))

#: Per-process memo of candidate-set digests, keyed by object identity. Safe
#: because a set is built fresh per line and never mutated, and the worst case of
#: an id being reused is a recomputation, never a wrong hash — the value is only
#: ever read back for the same live object.
_HASH_MEMO: dict[int, str] = {}


def _retrieve_for(company):
    """A retrieval callable bound to this company's tree, or one that finds nothing.

    Returning a no-op rather than `None` keeps the caller free of a branch: a
    company with no tree never reaches here, and an unbuilt index is already
    handled by `build_candidates_from_retrieval` degrading to the whole tree.

    Imported lazily because `rag.indexer` pulls in Qdrant and sentence
    transformers, and a sync that never narrows should not pay for either.
    """
    if company is None or company.spend_tree_id is None:
        return lambda query, top_k: []
    if not ai_config.CATEGORY_RETRIEVAL_ENABLED:
        return lambda query, top_k: []

    def retrieve(query: str, top_k: int):
        from ..rag.indexer import retrieve_categories

        return retrieve_categories(query, company.spend_tree_id, top_k=top_k)

    return retrieve


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
        # Assigned only when the ERP actually states one, and never over a
        # description a human settled.
        #
        # A plain assignment here wiped the field on every run, which mattered
        # the moment anything else wrote it: no connector states a vendor
        # description — Billy's contact book has no such field — so `v.description`
        # is None in practice, and the enrichment stage's work would have survived
        # exactly until the next sync. The catalog is global, so that is one
        # supplier's description lost for every tenant at once.
        if v.description and row.description_source != _HUMAN_DESCRIPTION:
            row.description = v.description
            row.description_source = _ERP_DESCRIPTION
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


def _has_human_lines(session: Session, invoice_id: str) -> bool:
    """Has anyone verified or hand-written a line on this invoice?

    Extraction replaces an invoice's lines **wholly**, so queueing one of these
    would discard a person's work automatically, on the strength of a document
    nobody asked us to re-read. The explicit `POST /invoices/{id}/reprocess` is
    a human decision and is unaffected — it is only the automatic path that
    yields.
    """
    return session.exec(
        select(InvoiceLine.id)
        .where(
            InvoiceLine.invoice_id == invoice_id,
            or_(
                InvoiceLine.status == LineStatus.VERIFIED,
                InvoiceLine.origin == LineOrigin.HUMAN,
            ),
        )
        .limit(1)
    ).first() is not None


def _queue_document(
    session: Session, row: Invoice, previous_file_id: Optional[str]
) -> bool:
    """Set ``doc_status`` for an invoice the sync is writing. True if it queued it.

    The runner queues documents; it never processes them. Five cases, and the
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
    * **Carries verified or human lines** — left alone. Replacement is
      whole-invoice, so queueing here would automatically discard work a person
      did. A human asking for a re-read still gets one.
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
    if _has_human_lines(session, row.id):
        return False
    row.doc_status = DocStatus.PENDING
    return True


def _assigner(session: Session, row, hard_reset: bool):
    """A setter for one row that respects what a human has settled.

    Returns ``assign(field, value)``. Ordinarily it skips a field listed in the
    row's ``verified_fields`` — the ERP is free to restate everything else, and
    that per-field granularity is the point: a reviewer who corrected a typo'd
    invoice number has said nothing about the total, and a genuine later
    re-posting of the total must still reach us.

    Under ``hard_reset`` it assigns anyway, audits the overwrite with actor
    ``system`` so the human's value stays recoverable, and drops the field from
    the settled set — a row must not go on claiming a field is verified at a
    value it no longer holds.

    A helper rather than a diff pass at the end of the loop: the skip stays
    visible at each assignment site, so a field added later cannot silently
    bypass the rule by being written the old way.
    """
    entity_type = "invoice" if isinstance(row, Invoice) else "invoice_line"

    def assign(field: str, value) -> None:
        if not is_verified(row, field):
            setattr(row, field, value)
            return
        if not hard_reset:
            return
        previous = getattr(row, field)
        setattr(row, field, value)
        clear_verified(row, [field])
        changes = diff_changes({field: previous}, {field: value}, (field,))
        if changes:
            record_audit(
                session, entity_type=entity_type, entity_id=row.id,
                action="hard_reset", changes=changes,
            )

    return assign


def _persist_invoices(
    session: Session,
    company_id: str,
    invoices: list[ErpInvoiceData],
    vendor_map: dict[str, str],
    fx: FxService,
    base_currency: str,
    fx_counts: dict[str, int],
    hard_reset: bool = False,
) -> tuple[dict[str, str], int, int, int, int]:
    """Upsert Invoice + InvoiceLine (+ scan File) as pending.

    The invoice is a purely internal scan: it references the File domain and is
    tied to entries via the voucher, but stores no ERP identity of its own (no
    ``erp_id``, no integration link — that provenance lives on the entries). The
    scan's ERP id is still used to derive a stable, deterministic invoice id so
    re-syncs upsert instead of duplicating.

    Returns ``(voucher_invoice_map, n_invoices, n_lines, n_queued, n_withdrawn)``
    where the map ties each scan's voucher to its persisted invoice id, so entries
    can be linked without the invoice storing the voucher, ``n_queued`` is how many
    invoices this run left waiting for document processing, and ``n_withdrawn`` how
    many lines the ERP stopped stating and this run therefore removed.
    """
    voucher_invoice_map: dict[str, str] = {}
    n_lines = 0
    n_queued = 0
    n_withdrawn = 0
    for inv in invoices:
        invoice_id = _det_id("invoice", company_id, inv.erp_id)
        vendor_id = vendor_map.get(inv.vendor_erp_id)
        file_id = _persist_file(session, company_id, invoice_id, inv)
        row = session.get(Invoice, invoice_id)
        if row is None:
            row = Invoice(id=invoice_id, company_id=company_id, status=InvoiceStatus.UNCATEGORIZED)
            session.add(row)
        previous_file_id = row.file_id
        assign = _assigner(session, row, hard_reset)
        assign("vendor_id", vendor_id)
        row.file_id = file_id
        if _queue_document(session, row, previous_file_id):
            n_queued += 1
        assign("invoice_number", inv.invoice_number)
        assign("invoice_date", inv.invoice_date)
        assign("currency", inv.currency)
        assign("total", _dec(inv.total))
        assign("tax", _dec(inv.tax))
        # Status is a rollup of the lines; not reset on re-sync.
        row.raw_json = inv.raw
        # Converted at the invoice's own date, never today's. `currency`,
        # `total` and `tax` above stay exactly as the ERP posted them.
        _safe_convert(fx_counts, lambda: fx.convert_invoice(row, base_currency))

        if inv.voucher_id is not None:
            voucher_invoice_map[inv.voucher_id] = invoice_id

        # An invoice holds exactly one *automated* origin at a time. Once a
        # document has been read, its lines are the better source — the only one
        # that knows what was actually bought — and re-adding the ERP's bill
        # lines beside them describes the same spend twice and doubles the
        # invoice's total. Extraction deletes the rows it replaces, which frees
        # the ERP's deterministic line ids, so without this the next sync
        # silently re-inserts every one of them.
        superseded = _superseding_origins(session, invoice_id)
        if superseded:
            n_withdrawn += _withdraw_superseded_erp_lines(session, invoice_id)
            continue

        stated_line_ids: set[str] = set()
        for idx, line in enumerate(inv.lines):
            line_key = line.line_erp_id or str(idx)
            line_id = _det_id("line", invoice_id, line_key)
            stated_line_ids.add(line_id)
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
            assign_line = _assigner(session, lrow, hard_reset)
            # A connector states one text and it names the item. `description`
            # stays null unless a connector genuinely states prose apart from
            # the name — none does today, and copying the same string into both
            # would make the distinction meaningless on the day it landed.
            assign_line("item_name", line.item_name or line.description)
            assign_line("description", line.description if line.item_name else None)
            assign_line("quantity", _dec(line.quantity))
            assign_line("unit", line.unit)
            assign_line("unit_price", _dec(line.unit_price))
            assign_line("amount", _dec(line.amount))
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

        # Guarded on the ERP having stated *something*: a bill that comes back
        # with no lines at all is far more likely a transient empty response
        # than a customer deleting every line, and wiping the invoice on one
        # would be unrecoverable.
        if stated_line_ids:
            n_withdrawn += _withdraw_unstated_lines(session, invoice_id, stated_line_ids)
    session.commit()
    return voucher_invoice_map, len(invoices), n_lines, n_queued, n_withdrawn


def _superseding_origins(session: Session, invoice_id: str) -> bool:
    """Whether a document has been read for this invoice.

    Only ``document_ai`` supersedes the ERP's own bill lines: the document is the
    single source that knows what was bought, and the two describe the same
    money.

    A ``human`` line deliberately does **not**. Splitting a stand-in means adding
    real lines beside it and then deleting it, so treating a human line as
    superseding would delete the very line the reviewer is working against,
    mid-operation. The reconciliation warning covers that intermediate state
    instead.
    """
    return session.exec(
        select(InvoiceLine.id).where(
            InvoiceLine.invoice_id == invoice_id,
            InvoiceLine.origin == LineOrigin.DOCUMENT_AI,
        ).limit(1)
    ).first() is not None


def _withdraw_superseded_erp_lines(session: Session, invoice_id: str) -> int:
    """Remove ERP-derived lines left beside a better source's.

    Prevention alone would leave every pair already stored, and an invoice whose
    lines sum to twice its total can never reconcile again. Audited like any
    other withdrawal, and `human` and `document_ai` lines are untouched.
    """
    doomed = session.exec(
        select(InvoiceLine).where(
            InvoiceLine.invoice_id == invoice_id,
            InvoiceLine.origin.in_(  # type: ignore[union-attr]
                (LineOrigin.ERP, LineOrigin.ENTRY_FALLBACK)
            ),
        )
    ).all()
    if not doomed:
        return 0

    doomed_ids = [line.id for line in doomed]
    for entry in session.exec(
        select(ErpEntry).where(ErpEntry.source_invoice_line_id.in_(doomed_ids))  # type: ignore[union-attr]
    ).all():
        entry.source_invoice_line_id = None
        session.add(entry)

    for line in doomed:
        record_audit(
            session,
            entity_type="invoice_line",
            entity_id=line.id,
            action=WITHDRAWN_ACTION,
            actor=SYSTEM_ACTOR,
            changes=[
                {"field": field, "old": _audit_value(line, field), "new": None}
                for field in _WITHDRAWN_FIELDS
            ],
        )
        session.delete(line)
    session.flush()
    recompute_invoice_status(session, invoice_id)
    return len(doomed)


def _withdraw_unstated_lines(
    session: Session, invoice_id: str, stated_ids: set[str]
) -> int:
    """Remove the invoice's ERP lines that this fetch did not restate.

    A line's identity is ``(invoice, line_erp_id)``, and an ERP may re-issue a
    line under a *new* id rather than mutating the old one — Billy does exactly
    that when a bill line is re-coded to another account. The replacement then
    lands as a second row and, with no prune, sits beside its predecessor for
    good: the invoice's lines sum to twice its total, it can never reconcile
    again, and its spend is double-counted wherever lines are summed.

    Only ``origin=ERP`` rows are eligible. A ``human`` line is a reviewer's own
    work and was never the ERP's to withdraw; a stand-in is keyed off its
    posting, not a line id, and is reconciled by the path that writes it.

    Returns the number removed. Does not commit — the caller owns the
    transaction, so the unlinking, the audit rows and the deletes land together.
    """
    doomed = [
        line for line in session.exec(
            select(InvoiceLine).where(
                InvoiceLine.invoice_id == invoice_id,
                InvoiceLine.origin == LineOrigin.ERP,
            )
        ).all()
        if line.id not in stated_ids
    ]
    if not doomed:
        return 0

    doomed_ids = [line.id for line in doomed]
    # Break the FK before deleting. Re-pointing the posting at the replacement
    # would mean matching on amount — the guessing the derived link refuses — so
    # unlinked is the honest end state, exactly as extraction leaves it.
    for entry in session.exec(
        select(ErpEntry).where(ErpEntry.source_invoice_line_id.in_(doomed_ids))  # type: ignore[union-attr]
    ).all():
        entry.source_invoice_line_id = None
        session.add(entry)

    for line in doomed:
        record_audit(
            session,
            entity_type="invoice_line",
            entity_id=line.id,
            action=WITHDRAWN_ACTION,
            actor=SYSTEM_ACTOR,
            changes=[
                {"field": field, "old": _audit_value(line, field), "new": None}
                for field in _WITHDRAWN_FIELDS
            ],
        )
        session.delete(line)

    # The categorizer recomputes this rollup, but only for an invoice that has
    # pending lines — so an invoice whose withdrawn line was its last unverified
    # one would keep a status describing lines that are gone.
    session.flush()
    recompute_invoice_status(session, invoice_id)
    return len(doomed)


def _audit_value(row, field: str):
    """A row's value for the audit trail, JSON-safe. Lines and postings alike."""
    value = getattr(row, field, None)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


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
    hard_reset: bool = False,
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
            # Through `_assigner`, like the ERP-line path above, so a field a
            # human settled is not overwritten. This path assigned directly
            # until now, which made the per-field guarantee a half-truth: the
            # API marked a reviewer's correction verified and the very next sync
            # wrote over it, on the one line kind most likely to need correcting.
            assign_line = _assigner(session, lrow, hard_reset)
            # Signed, exactly as `_net_spend` reads a posting: a credit on an
            # expense account is a refund and the line is negative.
            assign_line(
                "amount",
                (entry.debit_amount or _ZERO) - (entry.credit_amount or _ZERO),
            )
            # The posting's memo is the only statement of what was bought, so it
            # names the item. Frequently null — sometimes it is only the
            # counterparty's name — and null is left as null rather than
            # inventing a product.
            assign_line("item_name", entry.description)
            assign_line("description", None)
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


def _tree_candidates(session: Session, company_id: str) -> list | None:
    """The candidate set for a company: the nodes of the tree it is assigned.

    Returns ``None`` when the company has no assigned tree, which the caller
    treats as "do not categorize". There is deliberately **no fallback to the
    built-in taxonomy**: categories a customer never chose are untraceable, and
    an uncategorized line is an honest backlog where a wrongly-categorized one
    is a silent error that flows into every report and savings suggestion.
    """
    company = session.get(Company, company_id)
    if company is None or company.spend_tree_id is None:
        return None
    nodes = session.exec(
        select(SpendCategory).where(
            SpendCategory.spend_tree_id == company.spend_tree_id
        )
    ).all()
    if not nodes:
        return None
    return build_candidates_from_tree(nodes)


def _hash_for(offered) -> str:
    """The candidate set's digest, memoised per distinct set within a run.

    A run categorizes many lines against the same set, and hashing a few hundred
    node paths per line is real work for an answer that cannot have changed.
    """
    cached = _HASH_MEMO.get(id(offered))
    if cached is None:
        cached = tree_hash(offered)
        _HASH_MEMO[id(offered)] = cached
    return cached


def _match_from_cache(row: CategorizationCache, offered: list) -> CategoryMatch:
    """Rebuild an answer from a cached row, against the set it was given for.

    Resolved through ``offered`` rather than trusted from the row: the pointer is
    stored with no foreign key — one would make deleting a spend category fail on
    a *cache* row, a customer's tree edit refused by an optimization — so a node
    that has since gone resolves to nothing here and the line is simply left
    uncategorized for the next run to answer afresh.
    """
    node = next((c for c in offered if c.node_id == row.spend_category_id), None)
    if node is None:
        raise CategorizerUnavailable(
            "a cached answer names a category that is no longer offered"
        )
    return CategoryMatch(
        matched=True,
        spend_category_id=node.node_id,
        account_code=node.code,
        account_name=node.name,
        level_1=node.level(0), level_2=node.level(1),
        level_3=node.level(2), level_4=node.level(3),
        confidence=row.confidence or 0.0,
        rationale=row.rationale or "",
        gt_level_1=None, gt_level_2=None, gt_level_3=None, gt_account_code=None,
    )


def _index_tree(session: Session, company_id: str) -> None:
    """Embed the company's tree so retrieval has something to narrow against.

    Best-effort and never fatal. Qdrant being down, absent, or out of disk is not
    a reason to stop a ledger sync: without an index every line is simply offered
    the whole leaf set, which is what happened before retrieval existed and is
    exactly what `build_candidates_from_retrieval` degrades to.

    `build_tree_index` is itself idempotent by node count, so this is a no-op on
    every run after the first — and re-embeds after a node is added or removed,
    which is when the index would otherwise go stale.
    """
    if not ai_config.CATEGORY_RETRIEVAL_ENABLED:
        return
    company = session.get(Company, company_id)
    if company is None or company.spend_tree_id is None:
        return
    try:
        from ..rag.indexer import build_tree_index

        nodes = session.exec(
            select(SpendCategory).where(
                SpendCategory.spend_tree_id == company.spend_tree_id
            )
        ).all()
        build_tree_index(list(nodes), company.spend_tree_id)
    except Exception as exc:  # noqa: BLE001 - an index is an optimization
        logger.warning("    could not index the spend tree (%s); offering it whole", exc)


def _withdraw_voided_vouchers(
    session: Session, integration_id: str, voucher_ids: set[str]
) -> int:
    """Delete this integration's postings for vouchers the ERP has voided.

    Skipping a voided transaction at fetch time is not enough. One voided
    *after* we synced it is simply never mentioned again, so its postings stay —
    counting spend that was undone, and, because Billy re-books the same bill
    under a new transaction, putting one invoice under two vouchers with its
    lines rendered under both.

    Scoped to the ids the connector actually named. Absence from a fetch is not
    evidence of a void: a fetch is bounded by the watermark and by the account
    selection, so deleting on absence would delete the ledger.

    The invoice is **not** deleted with them. The bill is still a real bill; only
    the posting of it was undone, and the re-booking that follows needs an
    invoice to link to. Deleting it would also destroy any human correction and
    any line read from its document.

    Does not commit — the caller owns the transaction.
    """
    if not voucher_ids:
        return 0
    entries = session.exec(
        select(ErpEntry)
        .join(ErpAccount, ErpEntry.erp_account_id == ErpAccount.id)
        .where(
            ErpAccount.erp_integration_id == integration_id,
            ErpEntry.voucher_id.in_(voucher_ids),  # type: ignore[union-attr]
        )
    ).all()
    for entry in entries:
        record_audit(
            session,
            entity_type="erp_entry",
            entity_id=entry.id,
            action=VOIDED_ACTION,
            actor=SYSTEM_ACTOR,
            changes=[
                {"field": field, "old": _audit_value(entry, field), "new": None}
                for field in _VOIDED_ENTRY_FIELDS
            ],
        )
        session.delete(entry)
    if entries:
        logger.info("    withdrew %d posting(s) from %d voided voucher(s)",
                    len(entries), len(voucher_ids))
    return len(entries)


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

    # The ERP's own name for each account, looked up once. A posting-derived
    # line often has no description at all, and "Edb-udgifter / software" is
    # then the only statement of what was bought — a bare code is not.
    account_names = {
        code: name for code, name in session.exec(
            select(ErpAccount.erp_account_code, ErpAccount.erp_account_name)
            .where(ErpAccount.erp_integration_id == integration_id)
        ).all()
    }
    #: Vendor id -> (name, description). Looked up once per supplier, not once
    #: per line: a voucher with twenty lines names one supplier twenty times.
    vendors: dict[str, tuple[str, str | None]] = {}

    # Who is buying. Constant for the whole call, so resolved once here rather
    # than per line. A train ticket means something different to a haulier than
    # to a design studio.
    #
    # Only the name, because that is all a `Company` holds — there is no
    # description column, and inventing one is a schema change with a settings
    # field behind it, not something to smuggle in here. The name alone still
    # earns its place: "VectorLab ApS" tells a model more than nothing.
    company = session.get(Company, company_id)
    buyer_name = company.name if company else None
    # Narrowing is invisible when it works and invisible when it goes wrong, so
    # what it removed is reported per run rather than inferred from a bad answer.
    narrowed_total = 0
    lines_seen = 0

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
            if inv.vendor_id and inv.vendor_id not in vendors:
                vendor = session.get(Vendor, inv.vendor_id)
                vendors[inv.vendor_id] = (
                    (vendor.name, vendor.description) if vendor else ("", None)
                )
            vendor_name, vendor_description = vendors.get(inv.vendor_id or "", ("", None))
            # Narrow the tree to the neighbourhood of a plausible answer. A
            # no-op below `2 * top_k` leaves, and it degrades to the whole tree
            # whenever retrieval finds nothing or cannot be reached — never to a
            # shorter list the model then has to answer from.
            offered = build_candidates_from_retrieval(
                " ".join(part for part in (ln.item_name, ln.description) if part),
                candidates,
                _retrieve_for(company),
                top_k=CATEGORY_RETRIEVAL_TOP_K,
            )
            narrowed_total += len(candidates) - len(offered)
            lines_seen += 1

            supplier_name = vendor_name or (inv.supplier_name if inv else None)
            key = question_key(
                ln.item_name, ln.description, supplier_name, ln.native_account_code,
                vendor_description,
            )
            offered_hash = _hash_for(offered)
            cached = session.exec(
                select(CategorizationCache).where(
                    CategorizationCache.question_key == key,
                    CategorizationCache.tree_hash == offered_hash,
                )
            ).first()
            context = LineContext(
                # Both, separately. `item_name` is the field that is nearly
                # always set — reading only `description` here is what left the
                # model with a supplier and an amount and nothing else.
                item_name=ln.item_name,
                description=ln.description,
                native_account_code=ln.native_account_code,
                native_account_name=account_names.get(ln.native_account_code or ""),
                supplier=vendor_name or inv.supplier_name,
                # Null until the enrichment stage has run, which is the ordinary
                # state and costs nothing: an absent fact is simply not stated.
                supplier_description=vendor_description,
                buyer=buyer_name,
                amount=ln.amount,
                currency=inv.currency,
            )
            try:
                match = (
                    _match_from_cache(cached, offered)
                    if cached is not None
                    else categorize_line(context, offered)
                )
            except CategorizerUnavailable as exc:
                # Not this line's failure. Left `uncategorized`, it is picked up
                # by the next run; marked `ai_failed` it would need an explicit
                # requeue, so an outage would bury the whole batch.
                logger.warning("    categorizer unavailable, stopping: %s", exc)
                stats["unavailable"] = str(exc)
                session.commit()
                return stats

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
                ln.level_4 = match.level_4
                ln.account_code = match.account_code
                ln.account_name = match.account_name
                ln.confidence = _dec(match.confidence)
                ln.rationale = match.rationale
                # The matched node's own id — no lookup, so a match cannot land
                # on a real node and still store a null pointer.
                ln.spend_category_id = match.spend_category_id
                ln.status = LineStatus.AI_CATEGORIZED
                ln.error_message = None
                stats["categorized"] += 1
                if cached is None:
                    stats["cache_misses"] = stats.get("cache_misses", 0) + 1
                    session.add(CategorizationCache(
                        question_key=key, tree_hash=offered_hash,
                        spend_category_id=match.spend_category_id,
                        confidence=match.confidence, rationale=match.rationale,
                        question_sample=question_sample(
                            ln.item_name, supplier_name, ln.native_account_code
                        ),
                    ))
                else:
                    stats["cache_hits"] = stats.get("cache_hits", 0) + 1
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

    # What narrowing actually removed, per run. Logged rather than inferred: a
    # shortlist that excluded the right answer produces a wrong category with a
    # confident rationale, and nothing in the result distinguishes that from the
    # model simply being wrong. A reduction near 0% means retrieval is not
    # engaging; one near 100% means `top_k` is starving the prompt.
    if lines_seen:
        tree_size = len(candidates)
        average = narrowed_total / lines_seen
        logger.info(
            "    candidates: tree=%d avg_offered=%.1f avg_reduction=%.0f%% lines=%d",
            tree_size,
            tree_size - average,
            100.0 * average / tree_size if tree_size else 0.0,
            lines_seen,
        )

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
    hard_reset: bool = False,
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
        voucher_invoice_map, n_inv, n_lines, n_queued, n_withdrawn = _persist_invoices(
            session, company_id, invoices, vendor_map, fx, base_currency, fx_counts,
            hard_reset=hard_reset,
        )
        n_entries, n_linked = _persist_entries(
            session, company_id, integration_id, entries,
            voucher_invoice_map, account_map, fx, base_currency, fx_counts
        )
        # After persisting, so a voucher voided *and* restated in the same run
        # ends up withdrawn rather than half-written.
        n_entries_withdrawn = _withdraw_voided_vouchers(
            session, integration_id, connector.voided_voucher_ids()
        )
        session.commit()
        # After the entries, because a stand-in line stands in for a *posting* —
        # there is nothing to stand in for until they are persisted.
        n_standin = _persist_standin_lines(
            session, company_id, set(voucher_invoice_map.values()),
            fx, base_currency, fx_counts, hard_reset,
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
        candidates = _tree_candidates(session, company_id)
        _index_tree(session, company_id)
        categorization_skipped = None
        if candidates is None:
            # No taxonomy the customer chose ⇒ no categorization. The ledger
            # still landed above and the watermark still advances below: this is
            # a categorization failure, not a sync failure, and stalling the
            # ingest behind a settings gap would help nobody.
            categorization_skipped = (
                "no spend tree assigned to this company; lines were left uncategorized"
            )
            cat_stats = {
                "categorized": 0, "failed": 0,
                "invoices_completed": 0, "invoices_failed": 0,
                "skipped": categorization_skipped,
            }
            logger.warning("    skipped: %s", categorization_skipped)
        else:
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
        # `idle` with a reason, not `error`: the ERP side of the run succeeded
        # in full, and marking the integration failed would hide a real
        # connection failure behind a settings gap.
        _finish_sync_state(
            session, sync_state, invoices, status="idle", error=categorization_skipped
        )
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
        # A removal is the one thing a sync does that a re-run cannot undo, so
        # it is reported rather than left to the audit trail alone.
        summary["lines_withdrawn"] = n_withdrawn
        # A voided voucher's postings are deleted, which no re-run can undo, so
        # the count is reported rather than left to the audit trail alone.
        summary["entries_withdrawn"] = n_entries_withdrawn
        summary["base_currency"] = base_currency
        summary["fx"] = fx_counts
        return summary
    except Exception as exc:
        # The watermark is left where it was: a failed run has not advanced.
        _finish_sync_state(session, sync_state, [], status="error", error=str(exc))
        raise


def run_sync(
    *,
    since: date | None = None,
    integration_id: str | None = None,
    hard_reset: bool = False,
) -> dict[str, dict]:
    """Sync every connected ERP integration. Returns one summary per integration.

    Takes no tenant and no credentials: the work list is
    ``connected_integrations()`` and each connector is built from that
    integration's own stored credential. A failure is confined to the
    integration it happened to — the rest of the run continues.

    ``hard_reset`` restores the ERP's values over fields a human verified. It is
    the one and only override of that protection, opt-in, never implied by any
    other flag, and every overwrite it performs is audited with actor ``system``
    so the human's value stays recoverable. It does not delete human-added
    lines: it restores values, it is not a "drop everything the customer did"
    button.
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
                    session, integration, connector, since, fx, base_currency,
                    hard_reset=hard_reset,
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
    parser.add_argument(
        "--hard-reset", action="store_true",
        help="Overwrite fields a human verified with the ERP's values. Opt-in, "
             "audited as 'system', and never implied by any other flag. Human-added "
             "lines are not deleted.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    since = date.fromisoformat(args.since) if args.since else None
    if args.hard_reset:
        logger.warning(
            "--hard-reset: human-verified values will be overwritten by the ERP's "
            "(each one audited, so the overwritten value stays recoverable)"
        )

    try:
        results = run_sync(
            since=since, integration_id=args.integration_id, hard_reset=args.hard_reset
        )
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
