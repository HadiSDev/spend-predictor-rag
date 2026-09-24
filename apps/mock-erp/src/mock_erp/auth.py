"""Simple API-key auth for the mock ERP server."""

from fastapi import Header, HTTPException, status

EXPECTED_KEY = "mock-secret"


def verify_auth(x_app_secret_token: str = Header(...)) -> None:
    if x_app_secret_token != EXPECTED_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
