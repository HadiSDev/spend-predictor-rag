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
from ..fx import CONVERTED, UNCHANGED, UNCONVERTED
from ..fx.recompute import recompute_company
from ..integrations import integration_read, provision_integration
from ..schemas import (
    CompanyCreate,
    CompanyCreateResult,
    CompanyRead,
    CompanyUpdate,
    FxRecomputeResult,
)

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


@router.post("/companies", response_model=CompanyCreateResult,
             status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> CompanyCreateResult:
    """Create a company and connect its ERP in one transaction.

    A company with no integration syncs nothing, so the integration is required
    and both are committed together — a failure anywhere leaves no company.
    """
    organization_id = resolve_target_organization(scope, body.organization_id)
    company = Company(
        organization_id=organization_id,
        name=body.name,
        country_code=body.country_code,
        vat_number=body.vat_number,
        base_currency=body.base_currency,
    )
    session.add(company)
    # Model ids are client-side uuids, so the integration can reference the
    # company before any flush — one commit covers all three rows.
    try:
        integration = provision_integration(session, company.id, body.integration)
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(company)
    session.refresh(integration)

    return CompanyCreateResult(
        **CompanyRead.model_validate(company).model_dump(),
        integration=integration_read(integration),
    )


@router.patch("/companies/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: str,
    body: CompanyUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> Company:
    """Partial update, including `base_currency`.

    A base-currency change is saved on its own: already-converted rows keep the
    currency they were converted to until an explicit recompute rewrites them.
    Reports group by the stored base currency, so the in-between state shows up
    as two rows — visibly stale rather than silently wrong.
    """
    company = get_managed_company(session, scope, company_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@router.post("/companies/{company_id}/recompute-fx", response_model=FxRecomputeResult)
def recompute_company_fx(
    company_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> FxRecomputeResult:
    """Rewrite this company's stored base amounts against its current currency.

    Each row is reconverted at *its own* historical rate — this restates nothing
    at today's rate. Run it after switching base currency, or after enabling FX
    over data that was ingested unconverted.
    """
    company = get_managed_company(session, scope, company_id)
    try:
        counts = recompute_company(session, company.id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return FxRecomputeResult(
        company_id=company.id,
        base_currency=company.base_currency,
        converted=counts[CONVERTED],
        unconverted=counts[UNCONVERTED],
        unchanged=counts[UNCHANGED],
    )


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
