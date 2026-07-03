"""Invoice review endpoints — list and detail, scoped to the caller's org."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, select

from web_api.db.models import Invoice, InvoiceLine
from ..deps import TenantScope, get_session, resolve_company_ids, tenant_scope
from ..schemas import InvoiceDetailRead, InvoiceLineRead, InvoiceRead, Page

router = APIRouter(prefix="/api/v1", tags=["invoices"])


@router.get("/invoices", response_model=Page[InvoiceRead])
def list_invoices(
    status_filter: str | None = Query(default=None, alias="status"),
    company_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[Invoice]:
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
    return Page(items=rows, page=page, page_size=page_size, total=total)


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
    detail = InvoiceRead.model_validate(invoice).model_dump()
    detail["lines"] = [InvoiceLineRead.model_validate(line) for line in lines]
    return InvoiceDetailRead.model_validate(detail)
