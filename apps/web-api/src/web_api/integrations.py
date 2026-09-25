"""Provisioning an ERP integration for a company."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlmodel import Session, select

from web_api.db.models import ErpCredential, ErpIntegration

from .connectors import ErpConnector, available_connectors, connector_class, get_connector
from .credentials import decrypt_config, encrypt_config
from .schemas import ErpIntegrationRead, IntegrationSpec


def integration_read(integration: ErpIntegration) -> ErpIntegrationRead:
    """Non-secret view of an integration: credentials are reported, never returned."""
    data = ErpIntegrationRead.model_validate(integration)
    data.has_credentials = integration.credential is not None
    return data


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def validate_credentials(erp_type: str, credentials: dict) -> None:
    """Check a credentials map against the connector's declared fields."""
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
    """Validate and stage an integration (plus its credential) for ``company_id``."""
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


def connector_config(session: Session, integration: ErpIntegration) -> dict:
    """The integration's decrypted credentials, or ``{}`` for connector defaults."""
    credential = session.exec(
        select(ErpCredential).where(ErpCredential.erp_integration_id == integration.id)
    ).first()
    if credential is None:
        return {}
    try:
        return decrypt_config(credential.encrypted_config)
    except Exception as exc:
        raise RuntimeError(
            f"Could not decrypt credentials for integration {integration.id} — "
            "is WEB_API_CREDENTIAL_ENC_KEY set to the key they were written with?"
        ) from exc


def connector_for_integration(session: Session, integration: ErpIntegration) -> ErpConnector:
    """A configured connector for this integration."""
    return get_connector(integration.erp_type, connector_config(session, integration))
