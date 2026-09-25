"""The authenticated caller and how it is read from verified token claims."""
from __future__ import annotations

from dataclasses import dataclass

from web_api import config


class TokenVerificationError(Exception):
    """Raised when a token cannot be verified (bad signature, claims, key)."""


@dataclass(frozen=True)
class ClerkPrincipal:
    """The authenticated caller, extracted from a verified token."""

    user_id: str
    org_id: str | None
    org_name: str | None
    role: str | None
    email: str | None
    name: str | None
    is_system_admin: bool = False


_APP_ROLES = ("admin", "moderator", "member", "viewer")


def map_role(clerk_role: str | None) -> str:
    """Map a Clerk org role to an application role, defaulting to viewer."""
    r = (clerk_role or "").split(":")[-1].strip().lower()
    return r if r in _APP_ROLES else "viewer"


def _claim_truthy(value: object) -> bool:
    """Interpret a Clerk claim value as a boolean (handles bool/int/str)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def principal_from_claims(claims: dict) -> ClerkPrincipal:
    """Build a principal from verified JWT claims."""
    user_id = claims.get("sub")
    if not user_id:
        raise TokenVerificationError("token missing 'sub'")

    org_id = claims.get("org_id")
    role = claims.get("org_role")
    org_name = claims.get("org_slug")
    nested = claims.get("o")
    if isinstance(nested, dict):
        org_id = org_id or nested.get("id")
        role = role or nested.get("rol")
        org_name = org_name or nested.get("slg")

    claim_name = config.CLERK_SYSTEM_ADMIN_CLAIM
    is_system_admin = _claim_truthy(claims.get(claim_name)) if claim_name else False

    return ClerkPrincipal(
        user_id=user_id,
        org_id=org_id,
        org_name=org_name,
        role=role,
        email=claims.get("email"),
        name=claims.get("name") or claims.get("full_name"),
        is_system_admin=is_system_admin,
    )
