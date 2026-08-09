"""FastAPI dependency chain for the web API.

verify (get_verifier) -> get_principal -> current_user (JIT provisioning)
-> tenant_scope. Data routers depend only on ``tenant_scope`` and never accept
a tenant identifier from the client that widens access.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Generator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from web_api.db.models import Company, ErpIntegration, Organization, User
from web_api.db.session import engine
from .auth import ClerkPrincipal, TokenVerifier, TokenVerificationError, default_verifier
from .clerk_sync import provision_user

logger = logging.getLogger(__name__)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

# Matches a Python repr/quoted span, e.g. the `'bad-token'` in
# `f"unknown test token {token!r}"` — the idiomatic way a verifier embeds
# "the bad value" in a message.
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
# Matches anything JWT-shaped (three dot-separated base64url segments) that
# made it into a message unquoted.
_JWT_LIKE = re.compile(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")
# Bounds worst-case exposure regardless of what slips past both patterns.
_MAX_REASON_LENGTH = 200


def _sanitize_reason(message: str) -> str:
    """Scrub a verifier's failure message before it is logged.

    ``get_principal`` logs *why* a token was rejected so an intermittent 401
    is diagnosable — but the message text comes from whatever
    ``TokenVerifier`` is configured, and nothing here controls what that
    verifier puts in it. ``ClerkJwtVerifier`` today never embeds token text
    (its messages are static strings or ``str()`` of a PyJWT exception,
    neither of which echoes the input), but that is a property of *that*
    verifier's implementation, not of this logging call — a different or
    future verifier (or the test suite's own ``FakeVerifier``, which raises
    ``f"unknown test token {token!r}"``) could embed one. Treat the message
    as untrusted input rather than relying on every verifier to be careful:
    redact quoted spans (where "the bad value" idiomatically lives, keeping
    the surrounding words — that is where the actual classification is),
    redact anything JWT-shaped that slipped through unquoted, then cap the
    length. Ordinary PyJWT messages ("Signature has expired", "Invalid
    audience", ...) contain neither pattern and pass through unchanged, so
    the expired/bad-signature/unknown-kid distinction an operator needs
    survives.
    """
    scrubbed = _QUOTED.sub("'[redacted]'", message)
    scrubbed = _JWT_LIKE.sub("[redacted]", scrubbed)
    return scrubbed[:_MAX_REASON_LENGTH]


def get_verifier() -> TokenVerifier:
    """The token verifier. Overridden in tests via ``dependency_overrides``."""
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
        # Generic 401 — do not leak which check failed to the client. The reason
        # (expired, bad signature, unknown key, ...) is still worth having, so
        # it is logged server-side only — never put it in the response. The
        # message is untrusted (see `_sanitize_reason`): scrub it before it
        # ever reaches the log, rather than trusting the verifier not to have
        # embedded the token itself.
        logger.warning("Token verification failed: %s", _sanitize_reason(str(exc)))
        raise _UNAUTHORIZED


def current_user(
    principal: ClerkPrincipal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> User:
    user = provision_user(session, principal)
    # Suspended organizations block all access until reactivated.
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
    #: Every company in the org, active or not. This is the **authorization**
    #: set: what the caller may reach at all. A deactivated company is still
    #: theirs — its detail page must load and it has to be reactivatable — so
    #: this must never be narrowed to the active ones.
    company_ids: list[str]
    #: The subset that is active. This is the **listing** set: what an
    #: unfiltered "all companies" view covers. See `resolve_company_ids`.
    #: Required rather than defaulted: forgetting it would silently empty every
    #: listing in the API, which no test would obviously catch.
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
    """Resolve the effective company filter, validating any client-supplied id.

    A ``company_id`` that is not in the caller's scope raises 404 — never a
    window into another tenant's data.

    **Unfiltered means active companies only.** `GET /companies` already defaults
    to the active ones, so a client's company picker offers only those — and a
    deactivated company whose rows still appeared under "all companies" could not
    be filtered out by any request the client could make. Deactivating a company
    therefore takes it out of org-wide listings and report totals, which is what
    deactivating it is for.

    Asking for one **by id still works**, active or not: companies are
    soft-deactivated and never hard-deleted, so their history is retained and an
    explicit request for it is deliberate. Same shape as `GET /companies`, whose
    `include_inactive` reaches them on request.
    """
    if company_id is None:
        return scope.active_company_ids
    if company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return [company_id]


# -- Authorization -----------------------------------------------------------

_MANAGER_ROLES = {"admin", "moderator"}


def require_management(scope: TenantScope = Depends(tenant_scope)) -> TenantScope:
    """Allow only system admins or org admins/moderators. Others get 403."""
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


def resolve_target_organization(scope: TenantScope, organization_id: str | None) -> str:
    """Resolve which organization a write targets.

    Non–system-admins are confined to their own organization; a system admin may
    target any organization via an explicit ``organization_id``.
    """
    if organization_id is None or organization_id == scope.organization_id:
        return scope.organization_id
    if scope.is_system_admin:
        return organization_id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cannot act on another organization",
    )


def get_managed_company(session: Session, scope: TenantScope, company_id: str) -> Company:
    """Fetch a company the caller may manage, or raise 404.

    System admins may manage any company; others only within their organization.
    """
    company = session.get(Company, company_id)
    if company is None or (not scope.is_system_admin and company.id not in scope.company_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def get_managed_integration(
    session: Session, scope: TenantScope, integration_id: str
) -> ErpIntegration:
    """Fetch an ERP integration the caller may access, or raise 404.

    Scope is resolved through the integration's company: system admins may reach
    any integration; others only those whose company is in their organization.
    """
    integration = session.get(ErpIntegration, integration_id)
    if integration is None or (
        not scope.is_system_admin and integration.company_id not in scope.company_ids
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return integration
