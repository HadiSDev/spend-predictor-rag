"""Clerk session-token verifiers, framework-agnostic and unit-testable."""
from __future__ import annotations

from typing import Protocol

import jwt

from web_api import config

from .jwks import JwksCache
from .principal import ClerkPrincipal, TokenVerificationError, principal_from_claims


class TokenVerifier(Protocol):
    def verify(self, token: str) -> ClerkPrincipal:
        ...


class ClerkJwtVerifier:
    """Verifies Clerk RS256 session tokens against a cached JWKS."""

    def __init__(
        self,
        jwks_url: str,
        issuer: str,
        audience: str | None = None,
        jwks: JwksCache | None = None,
        leeway: float | None = None,
    ) -> None:
        self._issuer = issuer or None
        self._audience = audience or None
        self._jwks = jwks or (JwksCache(jwks_url) if jwks_url else None)
        self._leeway = (
            config.CLERK_CLOCK_SKEW_SECONDS if leeway is None else leeway
        )

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
                leeway=self._leeway,
                options={
                    "require": ["exp", "sub"],
                    "verify_aud": bool(self._audience),
                },
            )
        except TokenVerificationError:
            raise
        except jwt.PyJWTError as exc:
            raise TokenVerificationError(str(exc)) from exc
        return principal_from_claims(claims)


class DisabledVerifier:
    """Dev/test bypass: returns a fixed admin principal without verifying."""

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
