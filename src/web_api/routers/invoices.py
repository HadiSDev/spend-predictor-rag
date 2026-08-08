"""Invoice review endpoints — list, detail, and the scanned document."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from web_api.db.models import ErpAccount, ErpEntry, ErpIntegration, File, Invoice, InvoiceLine
from web_api.connectors.base import ErpConnectionError
from .. import integrations
from ..deps import TenantScope, get_session, resolve_company_ids, tenant_scope
from ..schemas import InvoiceDetailRead, InvoiceLineRead, InvoiceRead, Page

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


def _resolve_document_source(session: Session, invoice: Invoice) -> tuple[ErpIntegration, str]:
    """Which integration holds this invoice's document, and under which voucher.

    An invoice carries no integration id. The documented path is through its
    postings: entry -> erp_account -> erp_integration. An invoice with no
    postings falls back to the company's single connected integration, and 404s
    when there is none or more than one rather than guessing which ERP to ask.
    """
    row = session.exec(
        select(ErpEntry, ErpAccount)
        .join(ErpAccount, ErpAccount.id == ErpEntry.erp_account_id)
        .where(ErpEntry.source_invoice_id == invoice.id, ErpEntry.voucher_id.is_not(None))
        .order_by(ErpEntry.id)
    ).first()
    if row is not None:
        entry, account = row
        integration = session.get(ErpIntegration, account.erp_integration_id)
        if integration is not None and integration.disconnected_at is None:
            return integration, str(entry.voucher_id)

    candidates = session.exec(
        select(ErpIntegration).where(
            ErpIntegration.company_id == invoice.company_id,
            ErpIntegration.disconnected_at.is_(None),
        )
    ).all()
    if len(candidates) != 1 or invoice.invoice_number is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cannot determine which ERP holds this document",
        )
    return candidates[0], str(invoice.invoice_number)


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
    connector = integrations.connector_for_integration(session, integration)
    try:
        payload = connector.fetch_invoice_document(voucher_id)
    except ErpConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach the ERP to fetch this document: {exc}",
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
