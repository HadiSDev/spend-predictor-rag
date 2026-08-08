"""ERP integration controller: integration CRUD + connection actions + account
selection. Credentials are stored encrypted and never returned.

Everything here stays within ``web_api`` — it must not import ``ai_api``. The
live actions (test-connection, refresh-accounts) use the connector registry only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from web_api.db.models import ErpAccount, ErpCredential, ErpIntegration, User
from ..connectors import connector_catalog, get_connector
from ..credentials import decrypt_config, encrypt_config
from ..deps import (
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
    RefreshAccountsResult,
)

router = APIRouter(prefix="/api/v1", tags=["erp-integrations"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


#: Non-secret view of an integration; shared with the company-create path.
_read = integration_read


def _connector_config(integration: ErpIntegration) -> dict:
    """Decrypt the integration's stored credentials (empty dict if none)."""
    cred = integration.credential
    return decrypt_config(cred.encrypted_config) if cred is not None else {}


# -- Connector catalog -------------------------------------------------------


@router.get("/erp-types", response_model=list[ErpTypeRead], tags=["erp-types"])
def list_erp_types(_: User = Depends(current_user)) -> list[ErpTypeRead]:
    """The ERP systems this deployment can connect to.

    Authenticated but not management-gated: it exposes no tenant data and no
    secret values, only which connectors are registered and what each needs.
    """
    return [
        ErpTypeRead(
            erp_type=name,
            label=cls.label(),
            credential_fields=list(cls.credential_fields),
        )
        for name, cls in connector_catalog()
    ]


# -- Integrations ------------------------------------------------------------


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
        # Validate the requested company is in scope (404 otherwise).
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
    get_managed_company(session, scope, body.company_id)  # 404 if out of scope
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
        # Same field rules as creation — a typo'd key must not be stored here either.
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
    except Exception as exc:  # noqa: BLE001 - a failed probe is a result, not a 500
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
            # New account: our sync selection defaults to enabled, and the ERP's
            # VAT value is the best available starting assumption. Both are ours
            # from here on.
            row = ErpAccount(erp_integration_id=integration.id,
                             erp_account_code=acc.erp_account_code,
                             with_vat=acc.with_vat)
            session.add(row)
            added += 1
        # Refresh only what the ERP owns. `sync_enabled` and `with_vat` are
        # customer settings — a refresh that reset either would silently discard
        # a decision someone made. The ERP's own value stays recoverable in
        # `raw_json`.
        row.erp_account_name = acc.erp_account_name
        row.erp_account_type = acc.erp_account_type
        row.parent_code = acc.parent_code
        row.is_active = acc.is_active
        row.raw_json = acc.raw
    session.commit()
    return RefreshAccountsResult(seen=len(accounts), added=added)


# -- Accounts ----------------------------------------------------------------


@router.get("/erp-integrations/{integration_id}/accounts", response_model=list[ErpAccountRead])
def list_accounts(
    integration_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[ErpAccount]:
    get_managed_integration(session, scope, integration_id)  # 404 if out of scope
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
    # Enforce tenant scope through the parent integration (404 if out of scope).
    get_managed_integration(session, scope, account.erp_integration_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account
