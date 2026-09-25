"""Companies: list (read) + management (create / update / (de)activate)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from web_api.db.models import Company, InvoiceLine, LineStatus, SpendTree
from ..audit import record_audit
from ..db.models.audit_log import SYSTEM_ACTOR
from ..company_deletion import company_records, delete_company
from ..auth.deps import (
    TenantScope,
    get_managed_company,
    get_session,
    require_management,
    require_system_admin,
    resolve_target_organization,
    tenant_scope,
)
from ..fx import CONVERTED, UNCHANGED, UNCONVERTED
from ..fx.recompute import recompute_company
from ..integrations import integration_read, provision_integration
from ..schemas import (
    CompanyCreate,
    CompanyCreateResult,
    CompanyDeleteBlocked,
    CompanyDeleteResult,
    CompanyRead,
    CompanyUpdate,
    CompanyUpdateResult,
    FxRecomputeResult,
    RecategorizeResult,
)
from ..rollup import recompute_invoice_status
from ..spend_trees import service as tree_service
from ..spend_trees.reassign import reassign_company_tree

router = APIRouter(prefix="/api/v1", tags=["companies"])


def _company_read(session: Session, company: Company) -> CompanyRead:
    """A company payload with its spend tree's name resolved."""
    payload = CompanyRead.model_validate(company)
    if company.spend_tree_id:
        tree = session.get(SpendTree, company.spend_tree_id)
        payload.spend_tree_name = tree.name if tree else None
    return payload


def _resolve_tree_for_write(
    session: Session, organization_id: str, spend_tree_id: str | None
) -> str:
    """The tree a company write should land on."""
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
    """Create a company, connect its ERP, and give it a spend tree — one transaction."""
    organization_id = resolve_target_organization(scope, body.organization_id)
    try:
        spend_tree_id = _resolve_tree_for_write(session, organization_id, body.spend_tree_id)
    except Exception:
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
    """Partial update, including `base_currency` and `spend_tree_id`."""
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
    """Rewrite this company's stored base amounts against its current currency."""
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


REQUEUED_ACTION = "requeued_for_categorization"


@router.post("/companies/{company_id}/recategorize", response_model=RecategorizeResult)
def recategorize_company_lines(
    company_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> RecategorizeResult:
    """Return this company's `ai_failed` lines to `uncategorized`."""
    company = get_managed_company(session, scope, company_id)
    lines = session.exec(
        select(InvoiceLine).where(
            InvoiceLine.company_id == company.id,
            InvoiceLine.status == LineStatus.AI_FAILED,
        )
    ).all()

    try:
        for line in lines:
            changes = [
                {"field": "status", "old": line.status, "new": LineStatus.UNCATEGORIZED.value}
            ]
            for field in ("error_message", "rationale"):
                if getattr(line, field) is not None:
                    changes.append(
                        {"field": field, "old": getattr(line, field), "new": None}
                    )
            record_audit(
                session,
                entity_type="invoice_line",
                entity_id=line.id,
                action=REQUEUED_ACTION,
                actor=SYSTEM_ACTOR,
                changes=changes,
            )
            line.status = LineStatus.UNCATEGORIZED
            line.error_message = None
            line.rationale = None
            session.add(line)

        session.flush()
        for invoice_id in {line.invoice_id for line in lines}:
            recompute_invoice_status(session, invoice_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return RecategorizeResult(company_id=company.id, queued=len(lines))


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


@router.delete("/companies/{company_id}", response_model=CompanyDeleteResult)
def delete_company_endpoint(
    company_id: str,
    confirm: bool = Query(default=False),
    scope: TenantScope = Depends(require_system_admin),
    session: Session = Depends(get_session),
) -> CompanyDeleteResult:
    """Destroy a company and everything scoped to it."""
    company = get_managed_company(session, scope, company_id)
    records = company_records(session, company.id)

    if not records.is_empty and not confirm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CompanyDeleteBlocked(
                detail=(
                    "Deleting this company destroys its entire ledger, and it "
                    "cannot be undone. Deactivate it instead to retire it while "
                    "keeping the records. Send confirm=true to proceed."
                ),
                **records.__dict__,
            ).model_dump(mode="json"),
        )

    deleted = CompanyDeleteResult(
        id=company.id, name=company.name, **records.__dict__
    )
    try:
        delete_company(session, company)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return deleted
