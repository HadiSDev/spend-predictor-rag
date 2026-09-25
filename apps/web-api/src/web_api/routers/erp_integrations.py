"""ERP integration controller: integration CRUD + connection actions + account selection."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, select

from web_api.db.models import ErpAccount, ErpCredential, ErpEntry, ErpIntegration, User
from ..connectors import connector_catalog, get_connector
from ..credentials import decrypt_config, encrypt_config
from ..auth.deps import (
    TenantScope,
    current_user,
    get_managed_company,
    get_managed_integration,
    get_session,
    require_management,
    tenant_scope,
)
from ..integrations import (
    IntegrationSpec,
    integration_read,
    provision_integration,
    validate_credentials,
)
from ..schemas import (
    ConnectionTestResult,
    ErpAccountRead,
    ErpAccountUpdate,
    ErpIntegrationCreate,
    ErpIntegrationRead,
    ErpIntegrationUpdate,
    ErpTypeRead,
    IntegrationReplace,
    IntegrationReplaceBlocked,
    RefreshAccountsResult,
)

router = APIRouter(prefix="/api/v1", tags=["erp-integrations"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


_read = integration_read


def _connector_config(integration: ErpIntegration) -> dict:
    """Decrypt the integration's stored credentials (empty dict if none)."""
    cred = integration.credential
    return decrypt_config(cred.encrypted_config) if cred is not None else {}


@router.get("/erp-types", response_model=list[ErpTypeRead], tags=["erp-types"])
def list_erp_types(_: User = Depends(current_user)) -> list[ErpTypeRead]:
    """The ERP systems this deployment can connect to."""
    return [
        ErpTypeRead(
            erp_type=name,
            label=cls.label(),
            credential_fields=list(cls.credential_fields),
            brand_slug=cls.brand_slug,
            description=cls.description,
            docs_url=cls.docs_url,
        )
        for name, cls in connector_catalog()
    ]


@router.get("/erp-integrations", response_model=list[ErpIntegrationRead])
def list_integrations(
    company_id: str | None = Query(default=None),
    include_disconnected: bool = Query(default=False),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[ErpIntegrationRead]:
    if not scope.company_ids and not scope.is_system_admin:
        return []
    conditions = []
    if not scope.is_system_admin:
        conditions.append(ErpIntegration.company_id.in_(scope.company_ids))
    if company_id is not None:
        get_managed_company(session, scope, company_id)
        conditions.append(ErpIntegration.company_id == company_id)
    if not include_disconnected:
        conditions.append(ErpIntegration.disconnected_at.is_(None))

    rows = session.exec(select(ErpIntegration).where(*conditions).order_by(ErpIntegration.id)).all()
    return [_read(r) for r in rows]


@router.get("/erp-integrations/{integration_id}", response_model=ErpIntegrationRead)
def get_integration(
    integration_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> ErpIntegrationRead:
    return _read(get_managed_integration(session, scope, integration_id))


@router.post("/erp-integrations", response_model=ErpIntegrationRead,
             status_code=status.HTTP_201_CREATED)
def create_integration(
    body: ErpIntegrationCreate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> ErpIntegrationRead:
    get_managed_company(session, scope, body.company_id)
    integration = provision_integration(
        session,
        body.company_id,
        IntegrationSpec(
            erp_type=body.erp_type, label=body.label, credentials=body.credentials
        ),
    )
    session.commit()
    session.refresh(integration)
    return _read(integration)


@router.patch("/erp-integrations/{integration_id}", response_model=ErpIntegrationRead)
def update_integration(
    integration_id: str,
    body: ErpIntegrationUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> ErpIntegrationRead:
    integration = get_managed_integration(session, scope, integration_id)
    if body.label is not None:
        integration.label = body.label
        session.add(integration)
    if body.credentials is not None:
        validate_credentials(integration.erp_type, body.credentials)
        cred = integration.credential
        if cred is None:
            cred = ErpCredential(erp_integration_id=integration.id,
                                 encrypted_config=encrypt_config(body.credentials))
        else:
            cred.encrypted_config = encrypt_config(body.credentials)
            cred.updated_at = _now()
        session.add(cred)
    session.commit()
    session.refresh(integration)
    return _read(integration)


@router.post("/erp-integrations/{integration_id}/disconnect", response_model=ErpIntegrationRead)
def disconnect_integration(
    integration_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> ErpIntegrationRead:
    integration = get_managed_integration(session, scope, integration_id)
    integration.disconnected_at = _now()
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return _read(integration)


@router.post("/erp-integrations/{integration_id}/reconnect", response_model=ErpIntegrationRead)
def reconnect_integration(
    integration_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> ErpIntegrationRead:
    integration = get_managed_integration(session, scope, integration_id)
    integration.disconnected_at = None
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return _read(integration)


def _integration_history(session: Session, integration: ErpIntegration) -> dict:
    """What this integration has posted: entry count, invoice count, date span."""
    account_ids = select(ErpAccount.id).where(
        ErpAccount.erp_integration_id == integration.id
    )
    row = session.exec(
        select(
            func.count(ErpEntry.id),
            func.count(func.distinct(ErpEntry.source_invoice_id)),
            func.min(ErpEntry.accounting_date),
            func.max(ErpEntry.accounting_date),
        ).where(ErpEntry.erp_account_id.in_(account_ids))
    ).one()
    entries, invoices, earliest, latest = row
    return {
        "entries": entries or 0,
        "invoices": invoices or 0,
        "earliest": earliest,
        "latest": latest,
    }


@router.post(
    "/erp-integrations/{integration_id}/replace",
    response_model=ErpIntegrationRead,
    status_code=status.HTTP_201_CREATED,
)
def replace_integration(
    integration_id: str,
    body: IntegrationReplace,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> ErpIntegrationRead:
    """Move a company to a different ERP: retire the old, connect the new, once."""
    outgoing = get_managed_integration(session, scope, integration_id)

    if outgoing.disconnected_at is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This integration is already retired. Use "
                "POST /erp-integrations to connect a new one."
            ),
        )

    if body.erp_type == outgoing.erp_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This company is already connected to {outgoing.erp_type!r}. "
                "Use PATCH /erp-integrations/{id} to change its label or "
                "credentials; replacing would retire the integration and "
                "restart its sync from scratch."
            ),
        )

    validate_credentials(body.erp_type, body.credentials)

    if not body.confirm:
        history = _integration_history(session, outgoing)
        if history["entries"] or history["invoices"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=IntegrationReplaceBlocked(
                    detail=(
                        "This ERP has already posted to the ledger. Its data is "
                        "kept, and the new ERP will deliver overlapping periods "
                        "again as separate rows, so spend for those periods will "
                        "be counted twice. Send confirm=true to proceed."
                    ),
                    **history,
                ).model_dump(mode="json"),
            )

    try:
        outgoing.disconnected_at = _now()
        session.add(outgoing)
        incoming = provision_integration(
            session,
            outgoing.company_id,
            IntegrationSpec(
                erp_type=body.erp_type,
                label=body.label,
                credentials=body.credentials,
            ),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(incoming)
    return _read(incoming)


@router.post("/erp-integrations/{integration_id}/test-connection",
             response_model=ConnectionTestResult)
def test_connection(
    integration_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> ConnectionTestResult:
    integration = get_managed_integration(session, scope, integration_id)
    try:
        connector = get_connector(integration.erp_type, _connector_config(integration))
        connector.authorize()
        ok = connector.test_connection()
    except Exception as exc:  # noqa: BLE001
        return ConnectionTestResult(ok=False, message=str(exc))
    return ConnectionTestResult(ok=bool(ok), message=None if ok else "Connection test failed")


@router.post("/erp-integrations/{integration_id}/refresh-accounts",
             response_model=RefreshAccountsResult)
def refresh_accounts(
    integration_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> RefreshAccountsResult:
    integration = get_managed_integration(session, scope, integration_id)
    connector = get_connector(integration.erp_type, _connector_config(integration))
    connector.authorize()
    accounts = connector.fetch_accounts()

    existing = {
        a.erp_account_code: a
        for a in session.exec(
            select(ErpAccount).where(ErpAccount.erp_integration_id == integration.id)
        ).all()
    }
    added = 0
    for acc in accounts:
        row = existing.get(acc.erp_account_code)
        if row is None:
            row = ErpAccount(erp_integration_id=integration.id,
                             erp_account_code=acc.erp_account_code,
                             with_vat=acc.with_vat)
            session.add(row)
            added += 1
        row.erp_account_name = acc.erp_account_name
        row.erp_account_type = acc.erp_account_type
        row.parent_code = acc.parent_code
        row.is_active = acc.is_active
        row.raw_json = acc.raw
    session.commit()
    return RefreshAccountsResult(seen=len(accounts), added=added)


@router.get("/erp-integrations/{integration_id}/accounts", response_model=list[ErpAccountRead])
def list_accounts(
    integration_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[ErpAccount]:
    get_managed_integration(session, scope, integration_id)
    return session.exec(
        select(ErpAccount)
        .where(ErpAccount.erp_integration_id == integration_id)
        .order_by(ErpAccount.erp_account_code)
    ).all()


@router.patch("/erp-accounts/{account_id}", response_model=ErpAccountRead)
def update_account(
    account_id: str,
    body: ErpAccountUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> ErpAccount:
    account = session.get(ErpAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    get_managed_integration(session, scope, account.erp_integration_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account
