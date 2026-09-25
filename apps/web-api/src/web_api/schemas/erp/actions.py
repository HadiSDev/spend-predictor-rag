"""Results of connection actions on an integration."""
from __future__ import annotations

from pydantic import BaseModel


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str | None = None


class RefreshAccountsResult(BaseModel):
    seen: int
    added: int
