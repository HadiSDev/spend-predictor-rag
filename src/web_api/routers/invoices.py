"""Invoice review endpoints — list, detail, and the scanned document."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from web_api.db.models import (
    DocStatus, ErpAccount, ErpEntry, ErpIntegration, File, Invoice, InvoiceLine, Vendor,
)
from web_api.connectors.base import ErpConnectionError
from .. import integrations
from ..audit import INVOICE_AUDIT_FIELDS, INVOICE_BASE_FX_FIELDS, diff_changes, record_audit
from ..deps import TenantScope, get_session, require_management, resolve_company_ids, tenant_scope
from ..documents import resolve_document_source
from ..reconcile import reconcile_lines, totals_agree
from ..schemas import (
    InvoiceDetailRead, InvoiceLineRead, InvoiceRead, InvoiceUpdate, InvoiceVerify, Page,
)
from ..verified import mark_verified

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["invoices"])


#: The supplier fields an invoice may override, paired with the `Vendor` column
#: each falls back to. One mapping so the resolution and the override marker
#: cannot drift apart.
_SUPPLIER_FIELDS: tuple[tuple[str, str], ...] = (
    ("supplier_name", "name"),
    ("supplier_country_code", "country_code"),
    ("supplier_vat_number", "vat_number"),
)


def _get_scoped_invoice(session: Session, scope: TenantScope, invoice_id: str) -> Invoice:
    """Fetch an invoice the caller may reach, or 404. Never a window into another
    tenant: a foreign invoice is indistinguishable from a missing one."""
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


def _vendors_for(session: Session, invoices: list[Invoice]) -> dict[str, Vendor]:
    """The vendors these invoices point at, in one query."""
    vendor_ids = {i.vendor_id for i in invoices if i.vendor_id is not None}
    if not vendor_ids:
        return {}
    return {
        v.id: v for v in session.exec(select(Vendor).where(Vendor.id.in_(vendor_ids))).all()
    }


def _resolve_supplier(invoice: Invoice, vendor: Vendor | None) -> tuple[dict, list[str]]:
    """The supplier this invoice states, and which parts of it are a human's.

    `override ?? vendor.value`, computed here rather than in each client: the
    fallback is a rule, and a rule reimplemented per client is a rule that will
    eventually differ between two of them.

    An override is reported even when it equals the catalog value — it is still
    a human's assertion about this document, and marking it is what lets the UI
    offer the catalog value back.
    """
    resolved: dict = {}
    overridden: list[str] = []
    for field, vendor_field in _SUPPLIER_FIELDS:
        override = getattr(invoice, field)
        if override is not None:
            resolved[field] = override
            overridden.append(field)
        else:
            resolved[field] = getattr(vendor, vendor_field, None) if vendor else None
    return resolved, overridden


def _invoice_read(
    invoice: Invoice, file: File | None, vendor: Vendor | None = None
) -> InvoiceRead:
    """Build an `InvoiceRead`, resolving the file and the supplier.

    `file` and `vendor` are looked up by the caller (batched for a list, direct
    for a detail) rather than through the ORM relationships here, so neither
    path risks a lazy-load per row.
    """
    data = InvoiceRead.model_validate(invoice).model_dump()
    data["file_name"] = file.filename if file is not None else None
    data["has_document"] = file is not None
    resolved, overridden = _resolve_supplier(invoice, vendor)
    data.update(resolved)
    data["supplier_overrides"] = overridden
    # Computed here so a list row and an invoice detail cannot disagree about
    # it. Pure arithmetic over columns already on the row — no extra query.
    data["totals_agree"] = totals_agree(invoice)
    return InvoiceRead.model_validate(data)


@router.get("/invoices", response_model=Page[InvoiceRead])
def list_invoices(
    status_filter: str | None = Query(default=None, alias="status"),
    company_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[InvoiceRead]:
    company_ids = resolve_company_ids(scope, company_id)
    if not company_ids:
        return Page(items=[], page=page, page_size=page_size, total=0)

    conditions = [Invoice.company_id.in_(company_ids)]
    if status_filter is not None:
        conditions.append(Invoice.status == status_filter)

    total = session.exec(
        select(func.count()).select_from(Invoice).where(*conditions)
    ).one()
    rows = session.exec(
        select(Invoice)
        .where(*conditions)
        .order_by(Invoice.invoice_date.desc(), Invoice.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    file_ids = {r.file_id for r in rows if r.file_id is not None}
    files_by_id = {}
    if file_ids:
        files_by_id = {
            f.id: f
            for f in session.exec(select(File).where(File.id.in_(file_ids))).all()
        }
    # Batched for the same reason the files are: the supplier is resolved on
    # every row, and a per-row lookup would be one query per invoice on a page
    # of two hundred.
    vendors_by_id = _vendors_for(session, rows)
    items = [
        _invoice_read(r, files_by_id.get(r.file_id), vendors_by_id.get(r.vendor_id))
        for r in rows
    ]
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailRead)
def get_invoice(
    invoice_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> InvoiceDetailRead:
    invoice = _get_scoped_invoice(session, scope, invoice_id)
    lines = session.exec(
        select(InvoiceLine)
        .where(InvoiceLine.invoice_id == invoice_id)
        .order_by(InvoiceLine.sequence, InvoiceLine.id)
    ).all()
    file = session.get(File, invoice.file_id) if invoice.file_id is not None else None
    vendor = session.get(Vendor, invoice.vendor_id) if invoice.vendor_id is not None else None
    detail = _invoice_read(invoice, file, vendor).model_dump()
    detail["lines"] = [InvoiceLineRead.model_validate(line) for line in lines]
    verdict = reconcile_lines(lines, invoice)
    detail["lines_reconciled"] = verdict.ok
    detail["reconciliation_delta"] = verdict.delta
    return InvoiceDetailRead.model_validate(detail)


def _apply_header_corrections(
    session: Session, invoice: Invoice, corrections: dict
) -> list[dict]:
    """Apply header corrections in place, clear what they invalidate, audit.

    Shared by `PATCH /invoices/{id}` and `POST /invoices/{id}/verify` so the two
    cannot diverge in what they write, what they clear or what they record — the
    only difference between them is verification, which the caller adds.

    Returns the audit diff so the caller can tell an `edit` from a `noop`.
    """
    if corrections.get("vendor_id") is not None:
        if session.get(Vendor, corrections["vendor_id"]) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That supplier does not exist.",
            )

    before = {f: getattr(invoice, f) for f in INVOICE_AUDIT_FIELDS + INVOICE_BASE_FX_FIELDS}
    for field, value in corrections.items():
        setattr(invoice, field, value)

    # The base/FX columns were derived from the pre-correction
    # currency/total/tax; once one of those changes, the derived figures no
    # longer describe anything real. Per CLAUDE.md's currency-conversion
    # rules — "no rate ⇒ stored unconverted, never converted at a substitute
    # rate" and the base-currency-change precedent of leaving history
    # "visibly stale, not silently wrong" — we null them out rather than
    # recompute inline: this endpoint makes no network call, and an inline
    # reconversion is exactly what that philosophy rejects. The row then
    # reads honestly as "not converted" until an explicit recompute
    # (`POST /companies/{id}/recompute-fx`) runs. Do not "fix" this by
    # adding an inline FX call here.
    if any(getattr(invoice, f) != before[f] for f in ("currency", "total", "tax")):
        invoice.base_currency = None
        invoice.base_total = None
        invoice.base_tax = None
        invoice.fx_rate = None
        invoice.fx_rate_date = None

    session.add(invoice)
    after = {f: getattr(invoice, f) for f in INVOICE_AUDIT_FIELDS + INVOICE_BASE_FX_FIELDS}

    # "edit" only when a value actually moved; a PATCH that resubmits the
    # current value (or an empty body) is a "noop" — distinct from a real
    # correction so the audit feed never shows a change that didn't happen.
    # The diff also covers the base/FX fields above, so a cleared conversion
    # shows up in the trail even when the caller never asked for it directly.
    #
    # Because the correction is written **in place**, over the ERP's or the
    # extractor's own value, this diff's `old` is the only surviving record of
    # what was originally stated. There is no shadow column behind it.
    return diff_changes(before, after, INVOICE_AUDIT_FIELDS + INVOICE_BASE_FX_FIELDS)


def _read_after_write(session: Session, invoice: Invoice) -> InvoiceRead:
    """The saved invoice as a client reads it, with the supplier resolved."""
    session.refresh(invoice)
    file_row = session.get(File, invoice.file_id) if invoice.file_id is not None else None
    vendor = session.get(Vendor, invoice.vendor_id) if invoice.vendor_id is not None else None
    return _invoice_read(invoice, file_row, vendor)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceRead)
def update_invoice(
    invoice_id: str,
    body: InvoiceUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> InvoiceRead:
    """Correct a parsed invoice header (management only).

    Not gated on provenance. An ERP-posted header is as correctable as an
    extracted one: the extraction that produced either can be wrong, and the
    bookkeeper's own posting can be too. What keeps the correction from being
    erased by the next sync is the row's `verified_fields` (set by `verify`
    below), not a refusal to write here — and what keeps the ERP's original
    figure recoverable is the audit entry, not a second column.
    """
    invoice = _get_scoped_invoice(session, scope, invoice_id)
    changes = _apply_header_corrections(
        session, invoice, body.model_dump(exclude_unset=True)
    )
    record_audit(
        session, entity_type="invoice", entity_id=invoice.id,
        action="edit" if changes else "noop",
        actor=scope.user_id, changes=changes,
    )
    session.commit()
    return _read_after_write(session, invoice)


@router.post("/invoices/{invoice_id}/verify", response_model=InvoiceRead)
def verify_invoice(
    invoice_id: str,
    body: InvoiceVerify | None = None,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> InvoiceRead:
    """Verify a parsed invoice header (management only), optionally correcting it.

    The header counterpart of `POST /invoice-lines/{id}/verify`, and the same
    shape deliberately: one mental model covers both review surfaces.

    Verification is a distinct action from a correction because a human who
    reads a parsed field and leaves it alone has said something the extractor
    needs to hear — a `PATCH` cannot express "I looked, and it was right". That
    signal is what turns routine review into labelled data.

    The fields marked verified are the ones the caller **sent**, not the ones
    that changed: submitting `total: 2400` when 2400 is already stored is a
    human asserting that figure is correct. The audit action still says `noop`,
    because no value moved — the two records answer different questions.
    """
    invoice = _get_scoped_invoice(session, scope, invoice_id)
    corrections = body.model_dump(exclude_unset=True) if body is not None else {}
    changes = _apply_header_corrections(session, invoice, corrections)

    mark_verified(invoice, corrections.keys())
    invoice.verified_at = datetime.now(timezone.utc)
    invoice.verified_by = scope.user_id
    session.add(invoice)

    record_audit(
        session, entity_type="invoice", entity_id=invoice.id,
        action="edit" if changes else "verify",
        actor=scope.user_id, changes=changes,
    )
    session.commit()
    return _read_after_write(session, invoice)


@router.post("/invoices/{invoice_id}/reprocess", response_model=InvoiceRead)
def reprocess_invoice_document(
    invoice_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> InvoiceRead:
    """Queue this invoice's document to be read again (management only).

    The explicit way back from a failed extraction, and the only one: a sync
    deliberately does not requeue a `failed` invoice, because a document that
    has already proved unreadable does not become readable by being synced
    again. Resetting the attempt count is the point — the ceiling is what
    stopped the stage retrying, and a human asking for it is new information.

    Permitted on a `processed` invoice too, so a bad extraction can be redone
    once the extractor improves.
    """
    invoice = _get_scoped_invoice(session, scope, invoice_id)
    if invoice.file_id is None:
        # A pending invoice that can never succeed would sit in the queue
        # forever, so this is refused rather than accepted as a no-op.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invoice has no attached document, so there is nothing to process.",
        )
    if invoice.doc_status == DocStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invoice is being processed right now. Try again once it finishes.",
        )

    before = {"doc_status": invoice.doc_status, "doc_error": invoice.doc_error}
    invoice.doc_status = DocStatus.PENDING
    invoice.doc_error = None
    invoice.doc_attempts = 0
    session.add(invoice)
    record_audit(
        session, entity_type="invoice", entity_id=invoice.id, action="reprocess_document",
        actor=scope.user_id,
        changes=diff_changes(
            before, {"doc_status": invoice.doc_status, "doc_error": invoice.doc_error},
            ("doc_status", "doc_error"),
        ),
    )
    session.commit()
    return _read_after_write(session, invoice)


def _resolve_document_source(session: Session, invoice: Invoice) -> tuple[ErpIntegration, str]:
    """The HTTP face of `web_api.documents.resolve_document_source`.

    The rule itself lives in the domain because the ai_api document stage reads
    the same bytes from the same place; only the 404 is this layer's.
    """
    resolved = resolve_document_source(session, invoice)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cannot determine which ERP holds this document",
        )
    return resolved


@router.get("/invoices/{invoice_id}/document")
def get_invoice_document(
    invoice_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Response:
    """Stream the invoice's scanned document, fetched live from the ERP.

    Not stored locally: the document lives in the ERP, and copying it here would
    create a second source of truth to keep in sync. The trade-off is that this
    hits the ERP on every open — the first place to add a cache if it hurts.
    """
    invoice = _get_scoped_invoice(session, scope, invoice_id)
    if invoice.file_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No document attached to this invoice"
        )

    integration, voucher_id = _resolve_document_source(session, invoice)
    try:
        connector = integrations.connector_for_integration(session, integration)
    except RuntimeError as exc:
        # Credentials could not be decrypted (e.g. WEB_API_CREDENTIAL_ENC_KEY
        # rotated or unset). Our problem, not the caller's to see the detail of
        # — logged for an operator, reported to the client as a retryable
        # unavailability rather than a bare 500.
        logger.error(
            "could not build connector for integration %s (invoice %s): %s",
            integration.id, invoice_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The ERP connection for this document is not currently available.",
        ) from exc
    try:
        payload = connector.fetch_invoice_document(voucher_id)
    except ErpConnectionError as exc:
        # The ERP's raw error text (stack trace, internal hostname, ...) stays
        # server-side; the client gets a fixed, safe message.
        logger.warning(
            "document fetch failed for invoice %s (integration %s, voucher %s): %s",
            invoice_id, integration.id, voucher_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the ERP to fetch this document.",
        ) from exc
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="The ERP has no document for this voucher"
        )
    return Response(
        content=payload.content,
        media_type=payload.media_type,
        headers={"Content-Disposition": f'inline; filename="{payload.filename}"'},
    )
