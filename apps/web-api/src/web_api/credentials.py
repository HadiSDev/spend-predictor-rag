"""Encrypt/decrypt ERP integration credentials at rest."""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from . import config


class CredentialConfigError(HTTPException):
    """Raised when the encryption key is missing or a token cannot be read."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _fernet() -> Fernet:
    key = config.WEB_API_CREDENTIAL_ENC_KEY
    if not key:
        raise CredentialConfigError(
            "Credential encryption is not configured (WEB_API_CREDENTIAL_ENC_KEY unset)."
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise CredentialConfigError("Invalid WEB_API_CREDENTIAL_ENC_KEY.") from exc


def encrypt_config(config_dict: dict) -> str:
    """Encrypt a credential config dict to a Fernet token string."""
    token = _fernet().encrypt(json.dumps(config_dict, sort_keys=True).encode())
    return token.decode()


def decrypt_config(token: str) -> dict:
    """Decrypt a Fernet token string back to the credential config dict."""
    try:
        raw = _fernet().decrypt(token.encode() if isinstance(token, str) else token)
    except InvalidToken as exc:
        raise CredentialConfigError("Stored credentials could not be decrypted.") from exc
    return json.loads(raw.decode())


def generate_key() -> str:
    """Generate a fresh Fernet key (for populating the env var)."""
    return Fernet.generate_key().decode()
