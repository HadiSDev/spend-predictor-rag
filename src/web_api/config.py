"""Environment configuration for the business-domain / web API service.

Holds persistence and auth settings. AI/LLM settings live in ``ai_api.config``.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# PostgreSQL (transactions, vendors, recommendations, domain entities)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://spend_predictor:spend_predictor@localhost:5432/spend_predictor",
)

# Fernet key (urlsafe base64, 32 bytes) used to encrypt ERP integration
# credentials at rest. Required to create/update integration credentials; when
# unset those write paths fail closed rather than storing plaintext.
WEB_API_CREDENTIAL_ENC_KEY = os.getenv("WEB_API_CREDENTIAL_ENC_KEY", "")

# Web API auth (Clerk). The API is a resource server: it verifies Clerk-issued
# session JWTs against Clerk's JWKS. CLERK_ISSUER is the Clerk instance issuer
# (e.g. https://<slug>.clerk.accounts.dev); the JWKS URL defaults to the issuer's
# well-known endpoint. CLERK_AUDIENCE is validated only when set.
# WEB_API_AUTH_DISABLED bypasses verification for local dev/tests.
CLERK_ISSUER = os.getenv("CLERK_ISSUER", "")
CLERK_JWKS_URL = os.getenv(
    "CLERK_JWKS_URL",
    f"{CLERK_ISSUER.rstrip('/')}/.well-known/jwks.json" if CLERK_ISSUER else "",
)
CLERK_AUDIENCE = os.getenv("CLERK_AUDIENCE", "")
WEB_API_AUTH_DISABLED = os.getenv("WEB_API_AUTH_DISABLED", "false").lower() in ("1", "true", "yes")

# Tolerance, in seconds, for clock skew between Clerk's clock and this host's
# when checking `iat`/`nbf`/`exp`. Not zero: `iat` is stamped by Clerk and
# checked here, so a host running even a second behind rejects a perfectly good
# token with "The token is not yet valid (iat)" — a 401 that succeeds on retry
# once the wall clock catches up. 5s matches Clerk's own backend SDK default.
# It widens `exp` by the same amount, which is why it is small and not a minute:
# Clerk session tokens are short-lived, and this must not quietly extend one.
CLERK_CLOCK_SKEW_SECONDS = int(os.getenv("CLERK_CLOCK_SKEW_SECONDS", "5"))

# CORS: browser origins allowed to call the API (comma-separated). Empty means
# no cross-origin access — enabling a browser front-end is explicit. Dev sets
# e.g. WEB_API_CORS_ORIGINS=http://localhost:5173.
WEB_API_CORS_ORIGINS = [
    o.strip() for o in os.getenv("WEB_API_CORS_ORIGINS", "").split(",") if o.strip()
]

# Name of the Clerk token claim that marks a platform-level system admin.
# When the claim is truthy, the provisioned User gets is_system_admin=True.
CLERK_SYSTEM_ADMIN_CLAIM = os.getenv("CLERK_SYSTEM_ADMIN_CLAIM", "system_admin")

# Clerk webhooks (inbound) + Backend API (outbound org sync).
# CLERK_WEBHOOK_SIGNING_SECRET verifies Svix-signed webhook deliveries.
# CLERK_SECRET_KEY authenticates outbound Clerk Backend API calls.
# WEB_API_CLERK_OUTBOUND_DISABLED short-circuits outbound calls (dev/tests).
# How far an invoice's lines may be from its own total before they are judged
# not to reconcile. Relative *and* absolute, taking the larger: a percentage
# alone rejects a small invoice over one øre of rounding, and a fixed amount
# alone accepts a large invoice that is missing a whole line.
#
# In the domain rather than in `ai_api.config` because both the document
# extraction stage and the invoice payload's mismatch report read it, and
# `ai_api` imports `web_api` and never the reverse. `ai_api.config` re-exports
# these under the same names — the env vars are unchanged (DOC_ prefix and all,
# since renaming them would break every deployed .env for no gain).
DOC_RECONCILE_TOLERANCE_PCT = float(os.getenv("DOC_RECONCILE_TOLERANCE_PCT", "0.01"))
DOC_RECONCILE_TOLERANCE_ABS = float(os.getenv("DOC_RECONCILE_TOLERANCE_ABS", "1.00"))

# Historical FX rates (ECB daily reference rates via Frankfurter). Off by
# default: with FX_ENABLED unset nothing makes an outbound rate request and rows
# are simply stored unconverted, which is what keeps tests and offline runs
# hermetic. Already-cached rates in `fx_rates` keep working either way.
FX_ENABLED = os.getenv("FX_ENABLED", "false").lower() in ("1", "true", "yes")
FX_PROVIDER_URL = os.getenv("FX_PROVIDER_URL", "https://api.frankfurter.dev/v1")
FX_HTTP_TIMEOUT_SECONDS = float(os.getenv("FX_HTTP_TIMEOUT_SECONDS", "10"))

CLERK_WEBHOOK_SIGNING_SECRET = os.getenv("CLERK_WEBHOOK_SIGNING_SECRET", "")
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
CLERK_API_BASE_URL = os.getenv("CLERK_API_BASE_URL", "https://api.clerk.com/v1")
WEB_API_CLERK_OUTBOUND_DISABLED = os.getenv(
    "WEB_API_CLERK_OUTBOUND_DISABLED", "true"
).lower() in ("1", "true", "yes")
