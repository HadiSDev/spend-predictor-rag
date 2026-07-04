"""Pydantic response schemas for the web API (wire contract, not ORM)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """A paginated result envelope."""

    items: list[T]
    page: int
    page_size: int
    total: int


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    country_code: str | None = None
    vat_number: str | None = None
    is_active: bool = True
    deactivated_at: datetime | None = None


class CompanyCreate(BaseModel):
    """Request body to create a company. name is required."""

    name: str = Field(min_length=1)
    country_code: str | None = None
    vat_number: str | None = None
    # System admins may target another organization; ignored for other callers.
    organization_id: str | None = None


class CompanyUpdate(BaseModel):
    """Request body to update a company. All fields optional (partial update)."""

    name: str | None = Field(default=None, min_length=1)
    country_code: str | None = None
    vat_number: str | None = None


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str | None = None
    status: str
    created_at: datetime


class OrganizationUpdate(BaseModel):
    """Request body to update the organization profile."""

    name: str | None = Field(default=None, min_length=1)
    slug: str | None = Field(default=None, min_length=1)


class InvoiceLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    invoice_id: str
    company_id: str
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    native_account_code: str | None = None
    # Categorization lifecycle: uncategorized | ai_failed | ai_categorized | verified
    status: str
    # The categorization result, held directly on the line.
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    account_code: str | None = None
    account_name: str | None = None
    confidence: Decimal | None = None
    rationale: str | None = None
    # Accepted category assignment (null until it resolves to a real spend category).
    spend_category_id: str | None = None


class InvoiceLineVerify(BaseModel):
    """Verify a line, optionally correcting its category. Omitted fields are kept.

    Any provided field overwrites the AI result before the line is marked
    ``verified``; omitting the body accepts the AI result as-is.
    """

    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    account_code: str | None = None
    account_name: str | None = None
    confidence: Decimal | None = None
    rationale: str | None = None
    spend_category_id: str | None = None


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    action: str
    actor: str
    changes: list | None = None
    created_at: datetime


class ErpEntryRead(BaseModel):
    """A raw GL entry (posting). Entries are never categorized; raw_json is not exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    erp_account_id: str
    source_invoice_id: str | None = None
    voucher_id: str | None = None
    entry_type: str
    accounting_date: date | None = None
    description: str | None = None
    debit_amount: Decimal | None = None
    credit_amount: Decimal | None = None
    currency: str | None = None
    erp_entry_id: str | None = None
    status: str
    created_at: datetime


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    vendor_id: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    total: Decimal | None = None
    tax: Decimal | None = None
    status: str
    error_message: str | None = None


class InvoiceDetailRead(InvoiceRead):
    lines: list[InvoiceLineRead] = []


# -- ERP integrations & accounts ---------------------------------------------


class ErpIntegrationRead(BaseModel):
    """Non-secret view of an integration. Credentials are never included."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    erp_type: str
    label: str | None = None
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    created_at: datetime
    has_credentials: bool = False


class ErpIntegrationCreate(BaseModel):
    """Connect an integration. Credentials (base_url, api_key, …) are stored encrypted."""

    company_id: str
    erp_type: str = Field(min_length=1)
    label: str | None = None
    credentials: dict = Field(default_factory=dict)


class ErpIntegrationUpdate(BaseModel):
    """Partial update. Omitted `credentials` leaves the stored secret unchanged."""

    label: str | None = None
    credentials: dict | None = None


class ErpAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    erp_integration_id: str
    erp_account_code: str
    erp_account_name: str
    erp_account_type: str | None = None
    parent_code: str | None = None
    is_active: bool
    sync_enabled: bool
    with_vat: bool


class ErpAccountUpdate(BaseModel):
    sync_enabled: bool | None = None
    with_vat: bool | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str | None = None


class RefreshAccountsResult(BaseModel):
    seen: int
    added: int


# -- Reporting ---------------------------------------------------------------


class Report(BaseModel, Generic[T]):
    """Envelope for a small aggregate report (no pagination)."""

    rows: list[T]


class EntrySummaryRow(BaseModel):
    entry_type: str
    currency: str | None = None
    debit_total: Decimal
    credit_total: Decimal
    net: Decimal
    count: int


class EntryAccountRow(BaseModel):
    erp_account_id: str
    erp_account_code: str
    erp_account_name: str
    currency: str | None = None
    debit_total: Decimal
    credit_total: Decimal
    net: Decimal
    count: int


class CategorySpendRow(BaseModel):
    level_2: str | None = None
    level_3: str | None = None
    currency: str | None = None
    amount_total: Decimal
    count: int


class VendorSpendRow(BaseModel):
    vendor_id: str
    vendor_name: str
    currency: str | None = None
    amount_total: Decimal
    count: int
