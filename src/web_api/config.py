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

# Name of the Clerk token claim that marks a platform-level system admin.
# When the claim is truthy, the provisioned User gets is_system_admin=True.
CLERK_SYSTEM_ADMIN_CLAIM = os.getenv("CLERK_SYSTEM_ADMIN_CLAIM", "system_admin")

# Clerk webhooks (inbound) + Backend API (outbound org sync).
# CLERK_WEBHOOK_SIGNING_SECRET verifies Svix-signed webhook deliveries.
# CLERK_SECRET_KEY authenticates outbound Clerk Backend API calls.
# WEB_API_CLERK_OUTBOUND_DISABLED short-circuits outbound calls (dev/tests).
CLERK_WEBHOOK_SIGNING_SECRET = os.getenv("CLERK_WEBHOOK_SIGNING_SECRET", "")
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
CLERK_API_BASE_URL = os.getenv("CLERK_API_BASE_URL", "https://api.clerk.com/v1")
WEB_API_CLERK_OUTBOUND_DISABLED = os.getenv(
    "WEB_API_CLERK_OUTBOUND_DISABLED", "true"
).lower() in ("1", "true", "yes")
