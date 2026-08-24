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

# How far a document's lines may be from a total printed on the *same page*.
#
# Tighter than the pair above, and deliberately so: those size a comparison
# between two systems, where a supplier printing gross and a bookkeeper posting
# net are both correct. This one sizes arithmetic within one source, which ought
# to be near-exact — and on every real document examined for this rule it was
# exact to the øre (Aquatuning 88,95 + 15,90 = 104,85; CompuMail 15,07 + 484,00
# + 39,00 = 538,07; Fuluo US$75,00 + US$38,00 = US$113,00).
#
# The absolute floor is 0,10 rather than 0,01 because per-line rounding can
# drift a cent per line, and a fifteen-line invoice legitimately lands a few
# cents out. Provisional: sized from five documents, not from a distribution.
DOC_INTERNAL_TOLERANCE_PCT = float(os.getenv("DOC_INTERNAL_TOLERANCE_PCT", "0.001"))
DOC_INTERNAL_TOLERANCE_ABS = float(os.getenv("DOC_INTERNAL_TOLERANCE_ABS", "0.10"))

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

# Below this confidence, an AI categorization is treated as needing a human's
# eye. Configuration and not a column, the same discipline `category_stale`
# follows: it is a judgement about how much doubt is tolerable, it will be tuned
# once there is a confidence distribution worth tuning against, and every
# historical line has to move when it is. A stored flag would be a snapshot of
# the setting rather than a fact about the line.
#
# 0.6 is provisional. It is deliberately not derived from live data yet: every
# confidence currently on record was produced by a categorizer that could not see
# the lines it was scoring.
CATEGORIZATION_REVIEW_THRESHOLD = float(
    os.getenv("CATEGORIZATION_REVIEW_THRESHOLD", "0.6")
)
