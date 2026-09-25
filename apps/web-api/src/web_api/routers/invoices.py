"""Invoice review endpoints — list, detail, and the scanned document."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from web_api.db.models import (
    DocStatus, ErpIntegration, File, Invoice, InvoiceLine, Vendor,
)
from web_api.connectors.base import ErpConnectionError
from .. import integrations
from ..audit import INVOICE_AUDIT_FIELDS, INVOICE_BASE_FX_FIELDS, diff_changes, record_audit
from ..auth.deps import TenantScope, get_session, require_management, resolve_company_ids, tenant_scope
from ..documents import resolve_document_source
from ..reconcile import reconcile_lines, totals_agree
from ..schemas import (
    InvoiceDetailRead, InvoiceLineRead, InvoiceRead, InvoiceUpdate, InvoiceVerify, Page,
)
from ..verified import mark_verified

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["invoices"])


_SUPPLIER_FIELDS: tuple[tuple[str, str], ...] = (
    ("supplier_name", "name"),
    ("supplier_country_code", "country_code"),
    ("supplier_vat_number", "vat_number"),
)


def _get_scoped_invoice(session: Session, scope: TenantScope, invoice_id: str) -> Invoice:
    """Fetch an invoice the caller may reach, or 404."""
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
    """The supplier this invoice states, and which parts of it are a human's."""
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
    """Build an `InvoiceRead`, resolving the file and the supplier."""
    data = InvoiceRead.model_validate(invoice).model_dump()
    data["file_name"] = file.filename if file is not None else None
    data["has_document"] = file is not None
    resolved, overridden = _resolve_supplier(invoice, vendor)
    data.update(resolved)
    data["supplier_overrides"] = overridden
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
    """Apply header corrections in place, clear what they invalidate, audit."""
    if corrections.get("vendor_id") is not None:
        if session.get(Vendor, corrections["vendor_id"]) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That supplier does not exist.",
            )

    before = {f: getattr(invoice, f) for f in INVOICE_AUDIT_FIELDS + INVOICE_BASE_FX_FIELDS}
    for field, value in corrections.items():
        setattr(invoice, field, value)

    if any(getattr(invoice, f) != before[f] for f in ("currency", "total", "tax")):
        invoice.base_currency = None
        invoice.base_total = None
        invoice.base_tax = None
        invoice.fx_rate = None
        invoice.fx_rate_date = None

    session.add(invoice)
    after = {f: getattr(invoice, f) for f in INVOICE_AUDIT_FIELDS + INVOICE_BASE_FX_FIELDS}

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
    """Correct a parsed invoice header (management only)."""
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
    """Verify a parsed invoice header (management only), optionally correcting it."""
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
    """Queue this invoice's document to be read again (management only)."""
    invoice = _get_scoped_invoice(session, scope, invoice_id)
    if invoice.file_id is None:
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
    """The HTTP face of `web_api.documents.resolve_document_source`."""
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
    """Stream the invoice's scanned document, fetched live from the ERP."""
    invoice = _get_scoped_invoice(session, scope, invoice_id)
    if invoice.file_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No document attached to this invoice"
        )

    integration, voucher_id = _resolve_document_source(session, invoice)
    try:
        connector = integrations.connector_for_integration(session, integration)
    except RuntimeError as exc:
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
