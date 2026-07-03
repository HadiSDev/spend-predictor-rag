"""ERP entry (raw GL posting) read endpoints — list and detail, org-scoped."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, select

from web_api.db.models import ErpEntry
from ..deps import TenantScope, get_session, resolve_company_ids, tenant_scope
from ..schemas import ErpEntryRead, Page

router = APIRouter(prefix="/api/v1", tags=["erp-entries"])


@router.get("/erp-entries", response_model=Page[ErpEntryRead])
def list_erp_entries(
    company_id: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    voucher_id: str | None = Query(default=None),
    source_invoice_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[ErpEntry]:
    company_ids = resolve_company_ids(scope, company_id)
    if not company_ids:
        return Page(items=[], page=page, page_size=page_size, total=0)

    conditions = [ErpEntry.company_id.in_(company_ids)]
    if entry_type is not None:
        conditions.append(ErpEntry.entry_type == entry_type)
    if voucher_id is not None:
        conditions.append(ErpEntry.voucher_id == voucher_id)
    if source_invoice_id is not None:
        conditions.append(ErpEntry.source_invoice_id == source_invoice_id)
    if status_filter is not None:
        conditions.append(ErpEntry.status == status_filter)

    total = session.exec(
        select(func.count()).select_from(ErpEntry).where(*conditions)
    ).one()
    rows = session.exec(
        select(ErpEntry)
        .where(*conditions)
        .order_by(ErpEntry.entry_date.desc(), ErpEntry.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=rows, page=page, page_size=page_size, total=total)


@router.get("/erp-entries/{entry_id}", response_model=ErpEntryRead)
def get_erp_entry(
    entry_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> ErpEntry:
    entry = session.get(ErpEntry, entry_id)
    if entry is None or entry.company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return entry
