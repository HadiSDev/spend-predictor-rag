"""The inputs a connector needs to authenticate."""
from __future__ import annotations

from pydantic import BaseModel


class CredentialField(BaseModel):
    """One input a connector needs to authenticate."""

    name: str
    label: str
    required: bool = False
    secret: bool = False
    default: str | None = None
