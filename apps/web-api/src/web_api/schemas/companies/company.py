"""A company and the requests that create or change it."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..common import CurrencyCode
from ..erp.integration_replace import IntegrationSpec


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    country_code: str | None = None
    vat_number: str | None = None
    base_currency: str
    is_active: bool = True
    deactivated_at: datetime | None = None
    spend_tree_id: str | None = None
    spend_tree_name: str | None = None


class CompanyCreate(BaseModel):
    """Request body to create a company."""

    name: str = Field(min_length=1)
    base_currency: CurrencyCode
    country_code: str | None = None
    vat_number: str | None = None
    organization_id: str | None = None
    integration: IntegrationSpec
    spend_tree_id: str | None = None


class CompanyUpdate(BaseModel):
    """Request body to update a company."""

    name: str | None = Field(default=None, min_length=1)
    country_code: str | None = None
    vat_number: str | None = None
    base_currency: CurrencyCode | None = None
    spend_tree_id: str | None = None
