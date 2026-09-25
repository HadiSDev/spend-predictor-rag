"""The connector types a client can choose from."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CredentialFieldRead(BaseModel):
    """One input a connector needs."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    label: str
    required: bool = False
    secret: bool = False
    default: str | None = None


class ErpTypeRead(BaseModel):
    """A registered connector type, as offered to a client picker."""

    erp_type: str
    label: str
    credential_fields: list[CredentialFieldRead] = Field(default_factory=list)
    brand_slug: str | None = None
    description: str | None = None
    docs_url: str | None = None
