"""Companies: list (read) + management (create / update / (de)activate)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from web_api.db.models import Company, SpendTree
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
    CompanyUpdateResult,
    FxRecomputeResult,
)
from ..spend_trees import service as tree_service
from ..spend_trees.reassign import reassign_company_tree

router = APIRouter(prefix="/api/v1", tags=["companies"])


def _company_read(session: Session, company: Company) -> CompanyRead:
    """A company payload with its spend tree's name resolved.

    Resolved server-side for the same reason `ErpEntryRead` resolves its
    account: the row carries a foreign key, and a client showing "which taxonomy
    is this company on" would otherwise need a second request per company.
    """
    payload = CompanyRead.model_validate(company)
    if company.spend_tree_id:
        tree = session.get(SpendTree, company.spend_tree_id)
        payload.spend_tree_name = tree.name if tree else None
    return payload


def _resolve_tree_for_write(
    session: Session, organization_id: str, spend_tree_id: str | None
) -> str:
    """The tree a company write should land on.

    Omitted means the organization's copy of the default template, created here
    if this is its first company — so a company is never left without a taxonomy
    to categorize against, exactly as it is never left without an ERP
    connection. A tree from another organization is a 422, not a silent fallback.
    """
    if spend_tree_id is None:
        return tree_service.ensure_default_tree(session, organization_id).id

    tree = session.get(SpendTree, spend_tree_id)
    if tree is None or tree.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That spend tree does not belong to this organization.",
        )
    return tree.id


@router.get("/companies", response_model=list[CompanyRead])
def list_companies(
    include_inactive: bool = Query(default=False),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[CompanyRead]:
    if not scope.company_ids:
        return []
    stmt = select(Company).where(Company.organization_id == scope.organization_id)
    if not include_inactive:
        stmt = stmt.where(Company.is_active.is_(True))
    companies = session.exec(stmt.order_by(Company.name, Company.id)).all()
    return [_company_read(session, company) for company in companies]


@router.post("/companies", response_model=CompanyCreateResult,
             status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> CompanyCreateResult:
    """Create a company, connect its ERP, and give it a spend tree — one transaction.

    A company with no integration syncs nothing and a company with no taxonomy
    categorizes nothing, so both are settled here and committed together: a
    failure anywhere leaves no company, no integration, and no half-seeded tree.
    """
    organization_id = resolve_target_organization(scope, body.organization_id)
    try:
        spend_tree_id = _resolve_tree_for_write(session, organization_id, body.spend_tree_id)
    except Exception:
        # `ensure_default_tree` may have seeded a tree before a later failure.
        session.rollback()
        raise

    company = Company(
        organization_id=organization_id,
        name=body.name,
        country_code=body.country_code,
        vat_number=body.vat_number,
        base_currency=body.base_currency,
        spend_tree_id=spend_tree_id,
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
        **_company_read(session, company).model_dump(),
        integration=integration_read(integration),
    )


@router.patch("/companies/{company_id}", response_model=CompanyUpdateResult)
def update_company(
    company_id: str,
    body: CompanyUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> CompanyUpdateResult:
    """Partial update, including `base_currency` and `spend_tree_id`.

    A base-currency change is saved on its own: already-converted rows keep the
    currency they were converted to until an explicit recompute rewrites them.
    Reports group by the stored base currency, so the in-between state shows up
    as two rows — visibly stale rather than silently wrong.

    A **spend-tree change** is different: it is applied in the same transaction
    as the update, re-pointing every line whose stored path exists in the new
    tree and clearing the rest. Nothing is rewritten and no verification is
    lost; the response reports how many lines were left needing review, because
    the caller has to learn that at the moment they cause it.
    """
    company = get_managed_company(session, scope, company_id)
    changes = body.model_dump(exclude_unset=True)

    previous_tree_id = company.spend_tree_id
    new_tree_id = previous_tree_id
    if "spend_tree_id" in changes:
        new_tree_id = _resolve_tree_for_write(
            session, company.organization_id, changes.pop("spend_tree_id")
        )

    for field, value in changes.items():
        setattr(company, field, value)

    stale = 0
    if new_tree_id != previous_tree_id:
        company.spend_tree_id = new_tree_id
        stale = reassign_company_tree(session, company.id, previous_tree_id, new_tree_id)

    session.add(company)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(company)
    return CompanyUpdateResult(
        **_company_read(session, company).model_dump(), stale_lines=stale
    )


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
) -> CompanyRead:
    company = get_managed_company(session, scope, company_id)
    company.is_active = False
    company.deactivated_at = datetime.now(timezone.utc)
    session.add(company)
    session.commit()
    session.refresh(company)
    return _company_read(session, company)


@router.post("/companies/{company_id}/activate", response_model=CompanyRead)
def activate_company(
    company_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> CompanyRead:
    company = get_managed_company(session, scope, company_id)
    company.is_active = True
    company.deactivated_at = None
    session.add(company)
    session.commit()
    session.refresh(company)
    return _company_read(session, company)
