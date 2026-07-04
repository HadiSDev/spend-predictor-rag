"""Sync runner — the batch pipeline for the ERP Procurement Agent.

Orchestrates the full end-to-end flow against any ``ErpConnector``:

    connect → fetch → persist → categorize → aggregate → detect → recommend

It replaces the per-invoice PDF flow with batch processing of structured
transaction data. Deterministic: a given seed/connector state yields the same
rows and the same summary on every run.

Run it directly against the mock ERP API::

    python -m ai_api.sync.runner            # reset DB, sync mock data
    python -m ai_api.sync.runner --no-reset # incremental (keep rows)
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
    ErpAccount,
    ErpEntry,
    ErpIntegration,
    File,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    LineStatus,
    Organization,
    SpendCategory,
    SyncState,
    Vendor,
)
from ..persistence import LineGroundTruth
from ..procurement_agent import recommender
from ..redundancy import detector as redundancy
from web_api.audit import LINE_AUDIT_FIELDS, diff_changes, record_audit
from web_api.db.models.audit_log import SYSTEM_ACTOR
from web_api.db.session import engine
from web_api.rollup import recompute_invoice_status
from .categorizer import build_candidates, categorize

logger = logging.getLogger("ai_api.sync")

# Stable namespace so org/company/integration/entity IDs are reproducible across
# runs — re-syncing the same source is idempotent instead of duplicating rows.
_NS = uuid.UUID("5f4d6c3b-2a1e-4f8d-9c7b-0a1b2c3d4e5f")


def _det_id(*parts: str) -> str:
    return str(uuid.uuid5(_NS, ":".join(parts)))


def _dec(value) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


def _now() -> datetime:
    return datetime.now(timezone.utc)


# -- Bootstrap ---------------------------------------------------------------


def _bootstrap_tenant(
    session: Session, org_name: str, company_name: str, erp_type: str
) -> tuple[str, str]:
    """Ensure Organization, Company and ErpIntegration rows exist. Idempotent."""
    org_id = _det_id("org", org_name)
    company_id = _det_id("company", org_id, company_name)
    integration_id = _det_id("integration", company_id, erp_type)

    if session.get(Organization, org_id) is None:
        session.add(Organization(id=org_id, name=org_name))
    if session.get(Company, company_id) is None:
        session.add(Company(id=company_id, organization_id=org_id, name=company_name))
    integration = session.get(ErpIntegration, integration_id)
    if integration is None:
        integration = ErpIntegration(
            id=integration_id,
            company_id=company_id,
            erp_type=erp_type,
            label=f"{erp_type} integration",
            connected_at=_now(),
        )
        session.add(integration)
    session.commit()
    return company_id, integration_id


# -- Persist -----------------------------------------------------------------


def _persist_accounts(
    session: Session, integration_id: str, accounts: list[ErpAccountData]
) -> dict[str, str]:
    """Upsert ERP accounts. Returns {erp_account_code: erp_account_id} for entry linking."""
    mapping: dict[str, str] = {}
    for acc in accounts:
        acc_id = _det_id("erp_account", integration_id, acc.erp_account_code)
        row = session.get(ErpAccount, acc_id)
        if row is None:
            # New account: default our sync selection to enabled. Existing rows
            # keep whatever selection a user set — never reset from the ERP.
            row = ErpAccount(id=acc_id, erp_integration_id=integration_id,
                             erp_account_code=acc.erp_account_code)
            session.add(row)
        row.erp_account_name = acc.erp_account_name
        row.erp_account_type = acc.erp_account_type
        row.parent_code = acc.parent_code
        row.is_active = acc.is_active
        row.with_vat = acc.with_vat
        row.raw_json = acc.raw
        mapping[acc.erp_account_code] = acc_id
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
    file_id = _det_id("file", invoice_id, inv.file_name or inv.file_ref or "")
    row = session.get(File, file_id)
    if row is None:
        row = File(id=file_id, company_id=company_id, filename=inv.file_name or "scan.pdf",
                   file_type="invoice_pdf", storage_path=inv.file_ref or "")
        session.add(row)
    row.filename = inv.file_name or "scan.pdf"
    row.storage_path = inv.file_ref or ""
    row.status = "processed"
    return file_id


def _persist_invoices(
    session: Session,
    company_id: str,
    invoices: list[ErpInvoiceData],
    vendor_map: dict[str, str],
) -> tuple[dict[str, str], int, int]:
    """Upsert Invoice + InvoiceLine (+ scan File) as pending.

    The invoice is a purely internal scan: it references the File domain and is
    tied to entries via the voucher, but stores no ERP identity of its own (no
    ``erp_id``, no integration link — that provenance lives on the entries). The
    scan's ERP id is still used to derive a stable, deterministic invoice id so
    re-syncs upsert instead of duplicating.

    Returns ``(voucher_invoice_map, n_invoices, n_lines)`` where the map ties each
    scan's voucher to its persisted invoice id, so entries can be linked without
    the invoice storing the voucher.
    """
    voucher_invoice_map: dict[str, str] = {}
    n_lines = 0
    for inv in invoices:
        invoice_id = _det_id("invoice", company_id, inv.erp_id)
        vendor_id = vendor_map.get(inv.vendor_erp_id)
        file_id = _persist_file(session, company_id, invoice_id, inv)
        row = session.get(Invoice, invoice_id)
        if row is None:
            row = Invoice(id=invoice_id, company_id=company_id, status=InvoiceStatus.UNCATEGORIZED)
            session.add(row)
        row.vendor_id = vendor_id
        row.file_id = file_id
        row.invoice_number = inv.invoice_number
        row.invoice_date = inv.invoice_date
        row.currency = inv.currency
        row.total = _dec(inv.total)
        row.tax = _dec(inv.tax)
        # Status is a rollup of the lines; not reset on re-sync.
        row.raw_json = inv.raw

        if inv.voucher_id is not None:
            voucher_invoice_map[inv.voucher_id] = invoice_id

        for idx, line in enumerate(inv.lines):
            line_key = line.line_erp_id or str(idx)
            line_id = _det_id("line", invoice_id, line_key)
            lrow = session.get(InvoiceLine, line_id)
            if lrow is None:
                lrow = InvoiceLine(id=line_id, company_id=company_id,
                                   invoice_id=invoice_id, status=LineStatus.UNCATEGORIZED)
                session.add(lrow)
            lrow.description = line.description
            lrow.quantity = _dec(line.quantity)
            lrow.unit_price = _dec(line.unit_price)
            lrow.amount = _dec(line.amount)
            lrow.native_account_code = line.native_account_code
            # Status is NOT reset on re-sync: an already-categorized or verified
            # line keeps its lifecycle state (verified results are preserved).
            lrow.raw_json = line.raw
            n_lines += 1
    session.commit()
    return voucher_invoice_map, len(invoices), n_lines


def _persist_entries(
    session: Session,
    company_id: str,
    integration_id: str,
    entries: list[ErpEntryData],
    voucher_invoice_map: dict[str, str],
    account_map: dict[str, str],
) -> tuple[int, int]:
    """Upsert raw ErpEntry rows, linking each to its invoice via the voucher.

    Entries are stored as raw financial context and are NOT categorized. An
    entry's ``source_invoice_id`` is set from ``voucher_invoice_map`` when its
    voucher has an invoice scan; otherwise it stays NULL (payments, journals).
    Returns ``(n_entries, n_linked)``. Entries whose account is unknown to the
    persisted chart of accounts are skipped (the FK requires a known account).
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
        row.accounting_date = e.accounting_date
        row.description = e.description
        row.debit_amount = _dec(e.debit_amount)
        row.credit_amount = _dec(e.credit_amount)
        row.currency = e.currency
        row.erp_entry_id = e.erp_entry_id
        row.raw_json = e.raw
        n_entries += 1
        if source_invoice_id is not None:
            n_linked += 1
    session.commit()
    return n_entries, n_linked


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


def run_sync(
    erp_type: str = "mock",
    config: dict | None = None,
    *,
    org_name: str = "Demo Org",
    company_name: str = "Demo Company",
    since: date | None = None,
    reset: bool = False,
) -> dict:
    """Run a full sync cycle: connect → fetch → persist → categorize → downstream.

    Returns a summary dict. With ``reset=True`` the schema is dropped and
    recreated first, so the run is fully reproducible.
    """
    config = config or {}
    if reset:
        logger.info("Resetting database schema…")
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    # 1. Connect
    logger.info("[1/7] Connecting to %s ERP…", erp_type)
    connector: ErpConnector = get_connector(erp_type, config)
    connector.authorize()
    if not connector.test_connection():
        raise RuntimeError(f"Could not reach the {erp_type} ERP — is it running?")
    logger.info("  connection OK")

    with Session(engine) as session:
        company_id, integration_id = _bootstrap_tenant(
            session, org_name, company_name, erp_type
        )
        logger.info("  company=%s integration=%s", company_id, integration_id)

        sync_state = _begin_sync_state(session, integration_id)

        try:
            # 2. Fetch accounts + vendors, and persist accounts first so the
            #    sync selection (sync_enabled) is known before pulling entries.
            logger.info("[2/7] Fetching accounts & vendors…")
            accounts = connector.fetch_accounts()
            vendors = connector.fetch_vendors(since=since)
            account_map = _persist_accounts(session, integration_id, accounts)
            enabled_codes = _enabled_account_codes(session, integration_id)
            logger.info("  fetched %d accounts (%d enabled for sync), %d vendors",
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
            logger.info("  fetched %d entries (%d vouchers, %d invoice scans)",
                        len(entries), len(vouchers), len(invoices))

            # 3. Persist
            logger.info("[3/7] Persisting to PostgreSQL…")
            vendor_map = _persist_vendors(session, vendors)
            voucher_invoice_map, n_inv, n_lines = _persist_invoices(
                session, company_id, invoices, vendor_map
            )
            n_entries, n_linked = _persist_entries(
                session, company_id, integration_id, entries,
                voucher_invoice_map, account_map
            )
            logger.info("  persisted %d invoices, %d lines, %d entries (%d linked to an invoice)",
                        n_inv, n_lines, n_entries, n_linked)

            # 4. Categorize
            logger.info("[4/7] Categorizing pending invoice lines…")
            candidates = build_candidates(accounts)
            cat_stats = _categorize_pending(session, integration_id, company_id, candidates)
            logger.info("  categorized=%d failed=%d (invoices: %d completed, %d failed)",
                        cat_stats["categorized"], cat_stats["failed"],
                        cat_stats["invoices_completed"], cat_stats["invoices_failed"])

            # 5/6/7. Downstream (separate workstreams — wired as stubs for now)
            logger.info("[5/7] Aggregating spend…")
            _call_stub("spend_by_category", aggregation.spend_by_category, company_id)
            _call_stub("spend_by_vendor", aggregation.spend_by_vendor, company_id)
            logger.info("[6/7] Detecting redundant vendors…")
            _call_stub("same_category_overlaps", redundancy.find_same_category_overlaps, company_id)
            logger.info("[7/7] Generating savings recommendations…")
            _call_stub("recommendations", recommender.all_recommendations, company_id)

            summary = _build_summary(session, company_id)
            _finish_sync_state(session, sync_state, invoices, status="idle")
            logger.info("Sync complete: %s", summary)
            summary["company_id"] = company_id
            summary["categorization"] = cat_stats
            summary["accounts"] = len(accounts)
            summary["accounts_enabled"] = len(enabled_codes)
            return summary
        except Exception as exc:  # surface failure on the watermark, then re-raise
            _finish_sync_state(session, sync_state, [], status="error", error=str(exc))
            raise


def run_synthetic(
    *,
    base_url: str | None = None,
    api_key: str = "mock-secret",
    reset: bool = True,
    **kwargs,
) -> dict:
    """Generate data via the MockErpConnector (server-side, seeded) and sync it.

    The mock ERP API generates deterministic data from its seed; this simply
    runs the full pipeline against it. Used for dev, demo and benchmarking
    before real ERP data is available.
    """
    config: dict = {"api_key": api_key}
    if base_url:
        config["base_url"] = base_url
    return run_sync("mock", config, reset=reset, **kwargs)


# -- SyncState helpers -------------------------------------------------------


def _begin_sync_state(session: Session, integration_id: str) -> SyncState:
    state = SyncState(
        id=_det_id("sync_state", integration_id),
        erp_integration_id=integration_id,
        status="syncing",
    )
    session.merge(state)
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
    state.last_invoice_date = watermark
    state.status = status
    state.error_message = error
    session.merge(state)
    session.commit()


# -- CLI ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ERP procurement sync pipeline.")
    parser.add_argument("--erp-type", default="mock")
    parser.add_argument("--base-url", default=None,
                        help="Mock ERP base URL (default: connector default, http://localhost:8001)")
    parser.add_argument("--api-key", default="mock-secret")
    parser.add_argument("--org-name", default="Demo Org")
    parser.add_argument("--company-name", default="Demo Company")
    parser.add_argument("--since", default=None, help="ISO date watermark (incremental fetch)")
    parser.add_argument("--no-reset", dest="reset", action="store_false",
                        help="Keep existing rows instead of dropping the schema first")
    parser.set_defaults(reset=True)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    since = date.fromisoformat(args.since) if args.since else None
    config: dict = {"api_key": args.api_key}
    if args.base_url:
        config["base_url"] = args.base_url

    summary = run_sync(
        args.erp_type,
        config,
        org_name=args.org_name,
        company_name=args.company_name,
        since=since,
        reset=args.reset,
    )
    print("\n=== Sync summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
