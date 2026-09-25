"""Environment configuration for the business-domain / web API service."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_TRUTHY = ("1", "true", "yes")


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in _TRUTHY


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://steelyard:steelyard@localhost:5432/steelyard",
)

WEB_API_CREDENTIAL_ENC_KEY = os.getenv("WEB_API_CREDENTIAL_ENC_KEY", "")

CLERK_ISSUER = os.getenv("CLERK_ISSUER", "")
CLERK_JWKS_URL = os.getenv(
    "CLERK_JWKS_URL",
    f"{CLERK_ISSUER.rstrip('/')}/.well-known/jwks.json" if CLERK_ISSUER else "",
)
CLERK_AUDIENCE = os.getenv("CLERK_AUDIENCE", "")
WEB_API_AUTH_DISABLED = _env_flag("WEB_API_AUTH_DISABLED", "false")

CLERK_CLOCK_SKEW_SECONDS = int(os.getenv("CLERK_CLOCK_SKEW_SECONDS", "5"))

WEB_API_CORS_ORIGINS = [
    o.strip() for o in os.getenv("WEB_API_CORS_ORIGINS", "").split(",") if o.strip()
]

CLERK_SYSTEM_ADMIN_CLAIM = os.getenv("CLERK_SYSTEM_ADMIN_CLAIM", "system_admin")

DOC_RECONCILE_TOLERANCE_PCT = float(os.getenv("DOC_RECONCILE_TOLERANCE_PCT", "0.01"))
DOC_RECONCILE_TOLERANCE_ABS = float(os.getenv("DOC_RECONCILE_TOLERANCE_ABS", "1.00"))

DOC_INTERNAL_TOLERANCE_PCT = float(os.getenv("DOC_INTERNAL_TOLERANCE_PCT", "0.001"))
DOC_INTERNAL_TOLERANCE_ABS = float(os.getenv("DOC_INTERNAL_TOLERANCE_ABS", "0.10"))

FX_ENABLED = _env_flag("FX_ENABLED", "false")
FX_PROVIDER_URL = os.getenv("FX_PROVIDER_URL", "https://api.frankfurter.dev/v1")
FX_HTTP_TIMEOUT_SECONDS = float(os.getenv("FX_HTTP_TIMEOUT_SECONDS", "10"))

CLERK_WEBHOOK_SIGNING_SECRET = os.getenv("CLERK_WEBHOOK_SIGNING_SECRET", "")
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
CLERK_API_BASE_URL = os.getenv("CLERK_API_BASE_URL", "https://api.clerk.com/v1")
WEB_API_CLERK_OUTBOUND_DISABLED = _env_flag("WEB_API_CLERK_OUTBOUND_DISABLED", "true")

CATEGORIZATION_REVIEW_THRESHOLD = float(
    os.getenv("CATEGORIZATION_REVIEW_THRESHOLD", "0.6")
)
