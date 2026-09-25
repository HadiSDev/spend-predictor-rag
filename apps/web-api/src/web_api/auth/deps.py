"""FastAPI dependency chain for the web API."""
from __future__ import annotations

import logging
import re
from collections.abc import Generator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from web_api.db.models import Company, ErpIntegration, Organization, User
from web_api.db.session import engine

from .clerk_sync import provision_user
from .principal import ClerkPrincipal, TokenVerificationError
from .verifiers import TokenVerifier, default_verifier

logger = logging.getLogger(__name__)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_JWT_LIKE = re.compile(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")
_MAX_REASON_LENGTH = 200


def _sanitize_reason(message: str) -> str:
    """Scrub a verifier's failure message before it is logged."""
    scrubbed = _QUOTED.sub("'[redacted]'", message)
    scrubbed = _JWT_LIKE.sub("[redacted]", scrubbed)
    return scrubbed[:_MAX_REASON_LENGTH]


def get_verifier() -> TokenVerifier:
    """The token verifier."""
    return default_verifier()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def get_principal(
    authorization: str | None = Header(default=None),
    verifier: TokenVerifier = Depends(get_verifier),
) -> ClerkPrincipal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTHORIZED
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise _UNAUTHORIZED
    try:
        return verifier.verify(token)
    except TokenVerificationError as exc:
        logger.warning("Token verification failed: %s", _sanitize_reason(str(exc)))
        raise _UNAUTHORIZED


def current_user(
    principal: ClerkPrincipal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> User:
    user = provision_user(session, principal)
    org = session.get(Organization, user.organization_id)
    if org is not None and org.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is suspended",
        )
    return user


@dataclass(frozen=True)
class TenantScope:
    organization_id: str
    user_id: str
    role: str
    company_ids: list[str]
    active_company_ids: list[str]
    is_system_admin: bool = False


def tenant_scope(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> TenantScope:
    rows = session.exec(
        select(Company.id, Company.is_active).where(
            Company.organization_id == user.organization_id
        )
    ).all()
    return TenantScope(
        organization_id=user.organization_id,
        user_id=user.id,
        role=user.role,
        company_ids=[company_id for company_id, _ in rows],
        active_company_ids=[company_id for company_id, is_active in rows if is_active],
        is_system_admin=user.is_system_admin,
    )


def resolve_company_ids(scope: TenantScope, company_id: str | None) -> list[str]:
    """Resolve the effective company filter, validating any client-supplied id."""
    if company_id is None:
        return scope.active_company_ids
    if company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return [company_id]


_MANAGER_ROLES = {"admin", "moderator"}


def require_management(scope: TenantScope = Depends(tenant_scope)) -> TenantScope:
    """Allow only system admins or org admins/moderators."""
    if scope.is_system_admin or scope.role in _MANAGER_ROLES:
        return scope
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions to manage companies",
    )


def require_org_admin(scope: TenantScope = Depends(tenant_scope)) -> TenantScope:
    """Stricter gate for organization-profile changes: system admin or org admin."""
    if scope.is_system_admin or scope.role == "admin":
        return scope
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Organization admin required",
    )


def require_system_admin(scope: TenantScope = Depends(tenant_scope)) -> TenantScope:
    """The narrowest gate: a platform operator, not a customer's own admin."""
    if scope.is_system_admin:
        return scope
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="System administrator required",
    )


def resolve_target_organization(scope: TenantScope, organization_id: str | None) -> str:
    """Resolve which organization a write targets."""
    if organization_id is None or organization_id == scope.organization_id:
        return scope.organization_id
    if scope.is_system_admin:
        return organization_id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cannot act on another organization",
    )


def get_managed_company(session: Session, scope: TenantScope, company_id: str) -> Company:
    """Fetch a company the caller may manage, or raise 404."""
    company = session.get(Company, company_id)
    if company is None or (not scope.is_system_admin and company.id not in scope.company_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def get_managed_integration(
    session: Session, scope: TenantScope, integration_id: str
) -> ErpIntegration:
    """Fetch an ERP integration the caller may access, or raise 404."""
    integration = session.get(ErpIntegration, integration_id)
    if integration is None or (
        not scope.is_system_admin and integration.company_id not in scope.company_ids
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return integration
