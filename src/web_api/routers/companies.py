"""Companies: list (read) + management (create / update / (de)activate)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from web_api.db.models import Company, InvoiceLine, LineStatus, SpendTree
from ..audit import record_audit
from ..db.models.audit_log import SYSTEM_ACTOR
from ..company_deletion import company_records, delete_company
from ..deps import (
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


#: The audit action for a line put back in the categorizer's queue. Defined
#: beside its writer, as `withdrawn_by_erp` and `superseded_by_extraction` are.
REQUEUED_ACTION = "requeued_for_categorization"


@router.post("/companies/{company_id}/recategorize", response_model=RecategorizeResult)
def recategorize_company_lines(
    company_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> RecategorizeResult:
    """Return this company's `ai_failed` lines to `uncategorized`.

    **This queues; it does not categorize.** `web_api` does not import `ai_api`,
    so the categorizer runs only in the sync — and it processes exactly the
    `uncategorized` lines, which is what makes a status reset sufficient to
    requeue and why no flag or queue table is needed.

    Without this, `ai_failed` is terminal: the sync never retries a failure, so
    a line lost to a categorizer that has since improved could never be reached
    again short of hand-written SQL.

    Only `ai_failed` is eligible. `verified` is human authority and requeueing it
    would license an overwrite; `ai_categorized` did not fail, and resetting it
    would discard a usable result to re-derive it. Origin is deliberately not a
    filter — a stand-in line's spend is real spend, and most of a real ledger is
    stand-ins.
    """
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
            # The message describes an attempt that is no longer this line's
            # state; left in place it reports a queued line as still failing.
            if line.error_message is not None:
                changes.append(
                    {"field": "error_message", "old": line.error_message, "new": None}
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
            session.add(line)

        # In the same transaction: an invoice must never claim to be categorized
        # while the lines it rolls up from are sitting in the queue.
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
    """Destroy a company and everything scoped to it. There is no undo.

    For a company that should not exist — a typo, a trial that never synced, a
    test tenant, or one a customer asked to have removed. **Not** for retiring
    one whose ledger still means something: `POST /companies/{id}/deactivate`
    does that, keeps every record, and can be reversed.

    Refused with `409` and the counts until `confirm=true`, unless the company
    holds nothing — there is no point gating a preview of zero, and a dialog
    over nothing teaches the operator to click through the one that matters.

    System admin only. An org admin may deactivate; destroying a ledger is not
    something a support conversation can put right.
    """
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

    # Name and id are read before the delete: afterwards the object is gone from
    # the session and the response would have nothing to identify what went.
    deleted = CompanyDeleteResult(
        id=company.id, name=company.name, **records.__dict__
    )
    try:
        delete_company(session, company)
        session.commit()
    except Exception:
        # Atomic by construction — a failure part-way leaves the company exactly
        # as it was, rather than half a tenant with dangling children.
        session.rollback()
        raise
    return deleted
