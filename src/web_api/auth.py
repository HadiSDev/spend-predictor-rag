"""Clerk session-token verification (framework-agnostic, unit-testable).

The web API is a resource server: it verifies Clerk-issued RS256 session JWTs
against Clerk's JWKS. This module has no FastAPI dependency so the verifier can
be tested in isolation; the HTTP wiring lives in ``deps.py``.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Protocol

import httpx
import jwt

from web_api import config


class TokenVerificationError(Exception):
    """Raised when a token cannot be verified (bad signature, claims, key)."""


@dataclass(frozen=True)
class ClerkPrincipal:
    """The authenticated caller, extracted from a verified token."""

    user_id: str
    org_id: str | None
    org_name: str | None
    role: str | None  # raw Clerk org role (e.g. "org:admin")
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
    """Build a principal from verified JWT claims.

    Supports both the flat Clerk claims (``org_id``/``org_role``/``org_slug``)
    and the newer nested organization claim ``o = {id, rol, slg}``. The
    system-admin flag is read from the configured ``CLERK_SYSTEM_ADMIN_CLAIM``.
    """
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


class TokenVerifier(Protocol):
    def verify(self, token: str) -> ClerkPrincipal: ...


class JwksCache:
    """Fetches a JWKS over HTTP, caches keys by ``kid``, refreshes on a miss."""

    def __init__(self, jwks_url: str, http_get: Callable[[str], dict] | None = None) -> None:
        self._url = jwks_url
        self._http_get = http_get or self._default_get
        self._keys: dict[str, "jwt.PyJWK"] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _default_get(url: str) -> dict:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _load(self) -> None:
        data = self._http_get(self._url)
        keys: dict[str, jwt.PyJWK] = {}
        for entry in data.get("keys", []):
            kid = entry.get("kid")
            if kid:
                keys[kid] = jwt.PyJWK.from_dict(entry)
        with self._lock:
            self._keys = keys

    def get_key(self, kid: str) -> "jwt.PyJWK":
        with self._lock:
            key = self._keys.get(kid)
        if key is None:
            # Unknown kid — the signing keys may have rotated; refetch once.
            self._load()
            with self._lock:
                key = self._keys.get(kid)
        if key is None:
            raise TokenVerificationError(f"unknown signing key '{kid}'")
        return key


class ClerkJwtVerifier:
    """Verifies Clerk RS256 session tokens against a cached JWKS."""

    def __init__(
        self,
        jwks_url: str,
        issuer: str,
        audience: str | None = None,
        jwks: JwksCache | None = None,
    ) -> None:
        self._issuer = issuer or None
        self._audience = audience or None
        self._jwks = jwks or (JwksCache(jwks_url) if jwks_url else None)

    def verify(self, token: str) -> ClerkPrincipal:
        if self._jwks is None:
            raise TokenVerificationError("Clerk JWKS URL is not configured")
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            if not kid:
                raise TokenVerificationError("token header missing 'kid'")
            signing_key = self._jwks.get_key(kid)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience if self._audience else None,
                options={
                    "require": ["exp", "sub"],
                    "verify_aud": bool(self._audience),
                },
            )
        except TokenVerificationError:
            raise
        except jwt.PyJWTError as exc:  # signature/issuer/audience/expiry failures
            raise TokenVerificationError(str(exc)) from exc
        return principal_from_claims(claims)


class DisabledVerifier:
    """Dev/test bypass: returns a fixed admin principal without verifying.

    Enabled via ``WEB_API_AUTH_DISABLED`` for local development without Clerk.
    Never enable in production.
    """

    def verify(self, token: str) -> ClerkPrincipal:
        return ClerkPrincipal(
            user_id="dev-user",
            org_id="dev-org",
            org_name="Dev Org",
            role="admin",
            email="dev@example.com",
            name="Dev User",
        )


def default_verifier() -> TokenVerifier:
    """Build the verifier from configuration."""
    if config.WEB_API_AUTH_DISABLED:
        return DisabledVerifier()
    return ClerkJwtVerifier(
        jwks_url=config.CLERK_JWKS_URL,
        issuer=config.CLERK_ISSUER,
        audience=config.CLERK_AUDIENCE,
    )
