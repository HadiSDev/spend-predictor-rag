"""Companies: list (read) + management (create / update / (de)activate)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from web_api.db.models import Company
from ..deps import (
    TenantScope,
    get_managed_company,
    get_session,
    require_management,
    resolve_target_organization,
    tenant_scope,
)
from ..schemas import CompanyCreate, CompanyRead, CompanyUpdate

router = APIRouter(prefix="/api/v1", tags=["companies"])


@router.get("/companies", response_model=list[CompanyRead])
def list_companies(
    include_inactive: bool = Query(default=False),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[Company]:
    if not scope.company_ids:
        return []
    stmt = select(Company).where(Company.organization_id == scope.organization_id)
    if not include_inactive:
        stmt = stmt.where(Company.is_active.is_(True))
    return session.exec(stmt.order_by(Company.name, Company.id)).all()


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> Company:
    organization_id = resolve_target_organization(scope, body.organization_id)
    company = Company(
        organization_id=organization_id,
        name=body.name,
        country_code=body.country_code,
        vat_number=body.vat_number,
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@router.patch("/companies/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: str,
    body: CompanyUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> Company:
    company = get_managed_company(session, scope, company_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@router.post("/companies/{company_id}/deactivate", response_model=CompanyRead)
def deactivate_company(
    company_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> Company:
    company = get_managed_company(session, scope, company_id)
    company.is_active = False
    company.deactivated_at = datetime.now(timezone.utc)
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@router.post("/companies/{company_id}/activate", response_model=CompanyRead)
def activate_company(
    company_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> Company:
    company = get_managed_company(session, scope, company_id)
    company.is_active = True
    company.deactivated_at = None
    session.add(company)
    session.commit()
    session.refresh(company)
    return company
