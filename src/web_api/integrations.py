"""Provisioning an ERP integration for a company.

Shared by the two paths that can create one — `POST /api/v1/erp-integrations`
and `POST /api/v1/companies` — so both apply the same validation rules and
neither drifts from the other.

The helper **adds without committing**: the caller owns the transaction, which is
what lets company creation persist the company, its integration, and its
credential in a single commit.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlmodel import Session

from web_api.db.models import ErpCredential, ErpIntegration

from .connectors import available_connectors, connector_class
from .credentials import encrypt_config
from .schemas import ErpIntegrationRead, IntegrationSpec


def integration_read(integration: ErpIntegration) -> ErpIntegrationRead:
    """Non-secret view of an integration: credentials are reported, never returned."""
    data = ErpIntegrationRead.model_validate(integration)
    data.has_credentials = integration.credential is not None
    return data


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def validate_credentials(erp_type: str, credentials: dict) -> None:
    """Check a credentials map against the connector's declared fields.

    Undeclared keys are rejected rather than stored: a typo like ``apikey``
    would otherwise surface much later as an opaque auth failure during sync.
    """
    cls = connector_class(erp_type)
    if cls is None:
        raise _unprocessable(
            f"Unknown erp_type {erp_type!r}. Available: {', '.join(available_connectors())}"
        )
    declared = {f.name: f for f in cls.credential_fields}

    unknown = sorted(set(credentials) - set(declared))
    if unknown:
        raise _unprocessable(
            f"Unknown credential field(s) for {erp_type!r}: {', '.join(unknown)}. "
            f"Expected: {', '.join(sorted(declared)) or 'none'}"
        )

    missing = sorted(
        name
        for name, field in declared.items()
        if field.required and not str(credentials.get(name) or "").strip()
    )
    if missing:
        raise _unprocessable(
            f"Missing required credential field(s) for {erp_type!r}: {', '.join(missing)}"
        )


def provision_integration(
    session: Session,
    company_id: str,
    spec: IntegrationSpec,
) -> ErpIntegration:
    """Validate and stage an integration (plus its credential) for ``company_id``.

    Adds to the session without committing — the caller commits. Raises 422
    before adding anything if the connector or credentials are invalid.

    No `ErpCredential` row is written when the credentials map is empty, so a
    connector whose fields all have defaults can be connected without the
    credential encryption key being configured.
    """
    validate_credentials(spec.erp_type, spec.credentials)

    integration = ErpIntegration(
        company_id=company_id,
        erp_type=spec.erp_type,
        label=spec.label,
        connected_at=datetime.now(timezone.utc),
    )
    session.add(integration)

    if spec.credentials:
        session.add(
            ErpCredential(
                erp_integration_id=integration.id,
                encrypted_config=encrypt_config(spec.credentials),
            )
        )
    return integration
