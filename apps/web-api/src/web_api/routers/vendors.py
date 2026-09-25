"""Vendor list for the admin panel — the suppliers the caller's org transacts with."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlmodel import Session, select

from web_api.db.models import Invoice, Vendor
from ..auth.deps import TenantScope, get_session, resolve_company_ids, tenant_scope
from ..schemas import Page, VendorRead

router = APIRouter(prefix="/api/v1", tags=["vendors"])


@router.get("/vendors", response_model=Page[VendorRead])
def list_vendors(
    q: str | None = Query(default=None, description="Substring match on name or VAT number"),
    company_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[Vendor]:
    company_ids = resolve_company_ids(scope, company_id)
    if not company_ids:
        return Page(items=[], page=page, page_size=page_size, total=0)

    referenced = (
        select(Invoice.vendor_id)
        .where(Invoice.company_id.in_(company_ids), Invoice.vendor_id.is_not(None))
        .distinct()
    )
    conditions = [Vendor.id.in_(referenced)]
    if q:
        like = f"%{q}%"
        conditions.append(or_(Vendor.name.ilike(like), Vendor.vat_number.ilike(like)))

    total = session.exec(
        select(func.count()).select_from(Vendor).where(*conditions)
    ).one()
    rows = session.exec(
        select(Vendor)
        .where(*conditions)
        .order_by(Vendor.name, Vendor.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=rows, page=page, page_size=page_size, total=total)
