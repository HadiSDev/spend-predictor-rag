"""Invoice review endpoints — list, detail, and the scanned document."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from web_api.db.models import ErpAccount, ErpEntry, ErpIntegration, File, Invoice, InvoiceLine
from web_api.connectors.base import ErpConnectionError
from .. import integrations
from ..audit import INVOICE_AUDIT_FIELDS, INVOICE_BASE_FX_FIELDS, diff_changes, record_audit
from ..deps import TenantScope, get_session, require_management, resolve_company_ids, tenant_scope
from ..schemas import InvoiceDetailRead, InvoiceLineRead, InvoiceRead, InvoiceUpdate, Page

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["invoices"])


def _invoice_read(invoice: Invoice, file: File | None) -> InvoiceRead:
    """Build an `InvoiceRead`, resolving the file fields from its `File` row.

    `file` is looked up by the caller (batched for a list, direct for a
    detail) rather than through the ORM relationship here, so neither path
    risks a lazy-load per row.
    """
    data = InvoiceRead.model_validate(invoice).model_dump()
    data["file_name"] = file.filename if file is not None else None
    data["has_document"] = file is not None
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
    items = [_invoice_read(r, files_by_id.get(r.file_id)) for r in rows]
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailRead)
def get_invoice(
    invoice_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> InvoiceDetailRead:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    lines = session.exec(
        select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id).order_by(InvoiceLine.id)
    ).all()
    file = session.get(File, invoice.file_id) if invoice.file_id is not None else None
    detail = _invoice_read(invoice, file).model_dump()
    detail["lines"] = [InvoiceLineRead.model_validate(line) for line in lines]
    return InvoiceDetailRead.model_validate(detail)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceRead)
def update_invoice(
    invoice_id: str,
    body: InvoiceUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> Invoice:
    """Correct an AI-parsed invoice header (management only).

    409 for an ERP-sourced invoice: those values are evidence, and the only
    honest answer to a request to rewrite them is that they are not ours to
    rewrite.
    """
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.source != "pdf_extraction":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invoice came from the ERP; its posted values are evidence "
                   "and cannot be edited. Only AI-parsed invoices are correctable.",
        )

    before = {f: getattr(invoice, f) for f in INVOICE_AUDIT_FIELDS + INVOICE_BASE_FX_FIELDS}
    for field, value in body.model_dump(exclude_unset=True).items():
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
    changes = diff_changes(before, after, INVOICE_AUDIT_FIELDS + INVOICE_BASE_FX_FIELDS)
    record_audit(
        session, entity_type="invoice", entity_id=invoice.id,
        action="edit" if changes else "noop",
        actor=scope.user_id, changes=changes,
    )
    session.commit()
    session.refresh(invoice)
    return invoice


def _resolve_document_source(session: Session, invoice: Invoice) -> tuple[ErpIntegration, str]:
    """Which integration holds this invoice's document, and under which voucher.

    An invoice carries no integration id. The only path is through its
    postings: entry -> erp_account -> erp_integration, and every hop is
    re-scoped to the invoice's own company — an entry is trusted to name its
    integration, but never trusted to name one belonging to a *different*
    tenant, which a single bad sync row could otherwise cause.

    There is deliberately no fallback. Guessing a voucher id (the old
    fallback used `invoice.invoice_number`) is wrong on its face: a supplier's
    invoice number and the ERP's own voucher sequence are different
    namespaces, and a numeric supplier number can collide with a real voucher
    id and serve a document belonging to a different transaction entirely.
    Likewise, if the posting's own integration is disconnected, that is a
    404, not a cue to ask a *different* integration with a *different* key —
    the true voucher id was already in hand and is not transferable.
    """
    row = session.exec(
        select(ErpEntry, ErpAccount)
        .join(ErpAccount, ErpAccount.id == ErpEntry.erp_account_id)
        .where(
            ErpEntry.source_invoice_id == invoice.id,
            ErpEntry.company_id == invoice.company_id,
            ErpEntry.voucher_id.is_not(None),
        )
        .order_by(ErpEntry.id)
    ).first()
    if row is not None:
        entry, account = row
        integration = session.get(ErpIntegration, account.erp_integration_id)
        if (
            integration is not None
            and integration.disconnected_at is None
            and integration.company_id == invoice.company_id
        ):
            return integration, str(entry.voucher_id)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Cannot determine which ERP holds this document",
    )


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
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
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
