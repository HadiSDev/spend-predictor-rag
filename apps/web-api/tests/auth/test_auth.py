"""Auth tests: real JWT verification, JWKS cache behavior, and provisioning."""
from __future__ import annotations

import datetime as dt
import logging

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlmodel import Session, select

from web_api.auth import (
    ClerkJwtVerifier,
    JwksCache,
    TokenVerificationError,
    map_role,
)
from web_api.auth.deps import _sanitize_reason
from web_api.db.models import User
from web_api_testkit import auth

ISSUER = "https://test.clerk.example"


def _keypair(kid: str):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return priv, jwk


def _token(priv, kid, **claims):
    now = dt.datetime.now(dt.timezone.utc)
    payload = {"sub": "user_1", "iss": ISSUER, "iat": now, "exp": now + dt.timedelta(minutes=5)}
    payload.update(claims)
    return jwt.encode(payload, priv, algorithm="RS256", headers={"kid": kid})


def test_valid_token_is_verified_and_claims_extracted():
    priv, jwk = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", ISSUER, jwks=cache)

    token = _token(priv, "k1", org_id="org_9", org_role="org:admin", org_slug="Acme")
    principal = verifier.verify(token)

    assert principal.user_id == "user_1"
    assert principal.org_id == "org_9"
    assert principal.org_name == "Acme"
    assert map_role(principal.role) == "admin"


def test_moderator_role_and_system_admin_claim_are_extracted():
    priv, jwk = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", ISSUER, jwks=cache)

    token = _token(priv, "k1", org_id="org_9", org_role="org:moderator", system_admin=True)
    principal = verifier.verify(token)
    assert map_role(principal.role) == "moderator"
    assert principal.is_system_admin is True


def test_absent_system_admin_claim_defaults_false():
    priv, jwk = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", ISSUER, jwks=cache)
    principal = verifier.verify(_token(priv, "k1", org_id="org_9", org_role="org:admin"))
    assert principal.is_system_admin is False


def test_nested_org_claim_is_supported():
    priv, jwk = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", ISSUER, jwks=cache)

    token = _token(priv, "k1", o={"id": "org_x", "rol": "org:member", "slg": "Beta"})
    principal = verifier.verify(token)
    assert principal.org_id == "org_x"
    assert map_role(principal.role) == "member"


def test_expired_token_is_rejected():
    priv, jwk = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", ISSUER, jwks=cache)

    now = dt.datetime.now(dt.timezone.utc)
    token = jwt.encode(
        {"sub": "u", "iss": ISSUER, "exp": now - dt.timedelta(minutes=1)},
        priv, algorithm="RS256", headers={"kid": "k1"},
    )
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_token_issued_slightly_in_the_future_is_accepted():
    priv, jwk = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", ISSUER, jwks=cache)

    now = dt.datetime.now(dt.timezone.utc)
    token = _token(priv, "k1", org_id="org_9", iat=now + dt.timedelta(seconds=3))

    assert verifier.verify(token).user_id == "user_1"


def test_token_issued_far_in_the_future_is_still_rejected():
    priv, jwk = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", ISSUER, jwks=cache, leeway=5)

    now = dt.datetime.now(dt.timezone.utc)
    token = _token(priv, "k1", org_id="org_9", iat=now + dt.timedelta(minutes=10))

    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_leeway_does_not_resurrect_a_properly_expired_token():
    priv, jwk = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", ISSUER, jwks=cache, leeway=5)

    now = dt.datetime.now(dt.timezone.utc)
    token = _token(priv, "k1", org_id="org_9", exp=now - dt.timedelta(seconds=30))

    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_wrong_issuer_is_rejected():
    priv, jwk = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", "https://expected.issuer", jwks=cache)
    token = _token(priv, "k1")
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_signature_from_unknown_key_is_rejected():
    priv, jwk = _keypair("k1")
    other_priv, _ = _keypair("k1")
    cache = JwksCache("unused", http_get=lambda url: {"keys": [jwk]})
    verifier = ClerkJwtVerifier("unused", ISSUER, jwks=cache)
    token = _token(other_priv, "k1")
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_jwks_cache_caches_and_refreshes_on_unknown_kid():
    _, jwk1 = _keypair("k1")
    _, jwk2 = _keypair("k2")
    calls = {"n": 0}

    def http_get(url):
        calls["n"] += 1
        return {"keys": [jwk1]} if calls["n"] == 1 else {"keys": [jwk1, jwk2]}

    cache = JwksCache("unused", http_get=http_get)
    cache.get_key("k1")
    assert calls["n"] == 1
    cache.get_key("k1")
    assert calls["n"] == 1
    cache.get_key("k2")
    assert calls["n"] == 2
    with pytest.raises(TokenVerificationError):
        cache.get_key("nope")


def test_missing_authorization_header_is_401(client):
    assert client.get("/api/v1/companies").status_code == 401


def test_malformed_authorization_header_is_401(client):
    assert client.get("/api/v1/companies", headers={"Authorization": "Token x"}).status_code == 401


def test_invalid_token_is_401(client):
    assert client.get("/api/v1/companies", headers=auth("bad-token")).status_code == 401


def test_invalid_token_reason_is_logged_server_side_but_not_returned(client, caplog):
    with caplog.at_level(logging.WARNING, logger="web_api.auth.deps"):
        resp = client.get("/api/v1/companies", headers=auth("bad-token"))

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or missing credentials"}
    assert "bad-token" not in resp.text

    warnings = [r for r in caplog.records if r.name == "web_api.auth.deps"]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    message = warnings[0].getMessage()
    assert "bad-token" not in message
    assert "unknown test token" in message


def test_sanitize_reason_redacts_quoted_and_jwt_shaped_content():
    quoted = _sanitize_reason("unknown test token 'super-secret-value'")
    assert "super-secret-value" not in quoted
    assert "unknown test token" in quoted

    jwt_like = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyXzEifQ.c2lnbmF0dXJlLWJ5dGVzLWhlcmU"
    unquoted = _sanitize_reason(f"token rejected: {jwt_like}")
    assert jwt_like not in unquoted
    assert "token rejected" in unquoted

    assert _sanitize_reason("Signature has expired") == "Signature has expired"
    assert _sanitize_reason("Invalid audience") == "Invalid audience"


def test_health_is_unauthenticated(client):
    assert client.get("/api/v1/health").status_code == 200


def test_scalar_docs_served_and_swagger_disabled(client):
    scalar = client.get("/scalar")
    assert scalar.status_code == 200
    body = scalar.text.lower()
    assert "scalar" in body and "/openapi.json" in body
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 404


def test_first_request_provisions_user(client, engine):
    assert client.get("/api/v1/companies", headers=auth("tokA")).status_code == 200
    with Session(engine) as s:
        user = s.exec(select(User).where(User.clerk_user_id == "userA")).one()
        assert user.role == "admin"
        assert user.email == "a@a.com"


def test_provisioning_is_idempotent(client, engine):
    client.get("/api/v1/companies", headers=auth("tokA"))
    client.get("/api/v1/companies", headers=auth("tokA"))
    with Session(engine) as s:
        users = s.exec(select(User).where(User.clerk_user_id == "userA")).all()
        assert len(users) == 1


def test_unknown_role_maps_to_viewer(client, engine):
    client.get("/api/v1/companies", headers=auth("tok_weirdrole"))
    with Session(engine) as s:
        user = s.exec(select(User).where(User.clerk_user_id == "userD")).one()
        assert user.role == "viewer"


def test_user_without_org_is_403(client):
    assert client.get("/api/v1/companies", headers=auth("tok_noorg")).status_code == 403
