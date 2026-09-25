"""Suppliers as the admin panel lists them."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    country_code: str | None = None
    vat_number: str | None = None
    description: str | None = None
