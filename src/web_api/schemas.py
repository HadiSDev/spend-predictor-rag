"""Pydantic response schemas for the web API (wire contract, not ORM)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

T = TypeVar("T")


def _iso_4217(value: str) -> str:
    """Validate and normalize a currency code.

    Applied after the string check, so a non-string is a type error rather than
    an AttributeError. Uppercasing here means `dkk` and `DKK` are the same
    setting and the database only ever holds one form of it.
    """
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("must be a three-letter ISO 4217 currency code, e.g. 'DKK'")
    return code


CurrencyCode = Annotated[str, AfterValidator(_iso_4217)]

# Which currency an endpoint's *sums* are expressed in. `base` — the default —
# adds up the stored base-currency amounts, so a dimension yields one figure in
# the customer's own currency. `original` adds up the as-posted amounts and
# reproduces the pre-base-currency behaviour exactly. A Literal, so an
# unrecognised value is a 422 rather than a silent fallback.
CurrencyMode = Literal["base", "original"]


class Page(BaseModel, Generic[T]):
    """A paginated result envelope."""

    items: list[T]
    page: int
    page_size: int
    total: int


class IntegrationSpec(BaseModel):
    """An ERP connection to provision. Credentials are stored encrypted.

    Used both standalone and nested in company creation, so the two paths accept
    exactly the same shape.
    """

    erp_type: str = Field(min_length=1)
    label: str | None = None
    credentials: dict = Field(default_factory=dict)


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    country_code: str | None = None
    vat_number: str | None = None
    # The currency this company's figures are presented in. Returned on every
    # company payload so a client can format its amounts without a second call.
    base_currency: str
    is_active: bool = True
    deactivated_at: datetime | None = None


class CompanyCreate(BaseModel):
    """Request body to create a company.

    `name`, `base_currency` and `integration` are required: a company with no
    ERP connection syncs nothing, and one whose figures cannot be presented in a
    currency the customer reads is not a usable company either.
    """

    name: str = Field(min_length=1)
    base_currency: CurrencyCode
    country_code: str | None = None
    vat_number: str | None = None
    # System admins may target another organization; ignored for other callers.
    organization_id: str | None = None
    integration: IntegrationSpec


class CompanyUpdate(BaseModel):
    """Request body to update a company. All fields optional (partial update)."""

    name: str | None = Field(default=None, min_length=1)
    country_code: str | None = None
    vat_number: str | None = None
    # Changing this does NOT rewrite already-stored converted amounts — an
    # unbounded write has no business inside a PATCH. Rows are rewritten by
    # POST /companies/{id}/recompute-fx (or the backfill CLI).
    base_currency: CurrencyCode | None = None


class FxRecomputeResult(BaseModel):
    """What a recompute did. Counts are rows, across invoices, lines and entries."""

    company_id: str
    base_currency: str
    converted: int
    unconverted: int
    unchanged: int


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    role: str
    is_system_admin: bool
    organization_id: str


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    country_code: str | None = None
    vat_number: str | None = None
    description: str | None = None


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
    # The line in the company's base currency, at its invoice's rate. Null when
    # unconverted. A line's base amounts may not sum exactly to its invoice's —
    # each amount is converted from its own posted value, so a rounding
    # remainder is expected and is not reconciled away.
    base_currency: str | None = None
    base_amount: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_rate_date: date | None = None
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
    """A raw GL entry (posting). Entries are never categorized; raw_json is not exposed.

    The account and supplier are resolved server-side: an entry alone carries
    only foreign keys, and the vendor is not even one of them — it is reached
    through the source invoice. Rendering a posting would otherwise cost the
    client three lookups per row.
    """

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
    # The same posting in the company's own currency, plus the rate that got it
    # there. Carried on every entry regardless of the requested currency mode,
    # so a client can always explain a figure it shows. All null when the entry
    # could not be converted — never zero.
    base_currency: str | None = None
    base_debit_amount: Decimal | None = None
    base_credit_amount: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_rate_date: date | None = None
    status: str
    # Why a failed entry failed. Without it a bad sync is only visible in the
    # runner's stdout, never in the product.
    error_message: str | None = None
    created_at: datetime

    # Resolved from erp_account_id (a non-null FK, so always present).
    erp_account_code: str
    erp_account_name: str
    # expense | asset | liability | income, as the connector reported it. What
    # makes a posting's role legible: only the expense ones are spend, so this is
    # what lets a client show why a voucher's total is not the sum of its rows.
    erp_account_type: str | None = None
    # Resolved through source_invoice_id -> Invoice.vendor_id. Null when the
    # entry is not linked to an invoice, or that invoice has no vendor.
    vendor_id: str | None = None
    vendor_name: str | None = None

    # The invoice line this posting came from. One line has many entries, so
    # several postings can share it. Null for a posting with no line behind it.
    source_invoice_line_id: str | None = None
    # The line's spend category, resolved through that link.
    #
    # An entry is never itself categorized — categorization belongs to the
    # invoice line — but a client showing postings has to name the category that
    # applies to one, and would otherwise fetch the line per row. All three are
    # null both when the posting has no line and when its line is not yet
    # categorized; the two look the same on screen, and should.
    spend_category_level_1: str | None = None
    spend_category_level_2: str | None = None
    spend_category_level_3: str | None = None


class VoucherGroupRead(BaseModel):
    """The postings that make up one spend event.

    Pagination over these groups (rather than over entries) is what keeps a
    voucher's postings together: an entry-paginated list would cut a voucher in
    half at the page boundary and report totals for only part of it.
    """

    voucher_id: str | None = None
    company_id: str
    # The latest accounting_date among the group's entries; the sort axis.
    accounting_date: date | None = None
    entry_types: list[str] = []
    entry_count: int
    # Signed net spend: debit - credit over the group's *expense* postings only.
    # Not `debit_total - credit_total`, which is zero for any balanced voucher.
    # Null when the voucher moved money without spending any (a payment).
    amount: Decimal | None = None
    # Null only when every entry in the group is unconverted and the request
    # asked for base amounts — "we cannot say" rather than a zero that reads as
    # "nothing was spent".
    debit_total: Decimal | None = None
    credit_total: Decimal | None = None
    # Claimed only when every entry in the group agrees; null otherwise. When
    # `currency` is null the totals span currencies and must not be shown as one
    # amount. In base mode the agreement is on `base_currency`, so a voucher
    # posted in two currencies but converted to one reports that one.
    currency: str | None = None
    # How many of the group's entries have no base amount, and are therefore
    # excluded from the totals above. Always 0 in original mode, where nothing
    # is excluded. A non-zero count means the total shown is incomplete.
    unconverted_count: int = 0
    vendor_id: str | None = None
    vendor_name: str | None = None
    entries: list[ErpEntryRead] = []


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
    # The invoice in the company's base currency, at the rate in force on
    # `invoice_date`. Null when unconverted; `currency`/`total`/`tax` above are
    # always the as-posted figures.
    base_currency: str | None = None
    base_total: Decimal | None = None
    base_tax: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_rate_date: date | None = None
    status: str
    # 'erp' | 'pdf_extraction' — see Invoice.source.
    source: str = "erp"
    error_message: str | None = None
    file_id: str | None = None
    # Resolved from the linked File so a client never needs a second lookup to
    # decide whether to render a viewer.
    file_name: str | None = None
    has_document: bool = False


class InvoiceDetailRead(InvoiceRead):
    lines: list[InvoiceLineRead] = []


class DocumentRead(BaseModel):
    """The document attached to a voucher's invoice. Derived from
    `Invoice.file_id`/`File.filename` — never an independent source of truth."""

    file_id: str
    filename: str


class VoucherDetailRead(BaseModel):
    """Everything one voucher's detail panel needs, in one request.

    Exists for the cold load: `GET /erp-entries/vouchers` already embeds each
    group's entries, so a panel opened from the table has its postings already.
    A shared link arriving at an unfiltered page does not, and also needs the
    invoice, its lines, and the document descriptor.
    """

    voucher_id: str | None = None
    company_id: str
    accounting_date: date | None = None
    currency: str | None = None
    entry_count: int
    entries: list[ErpEntryRead] = []
    invoice: InvoiceDetailRead | None = None
    document: DocumentRead | None = None


# -- ERP integrations & accounts ---------------------------------------------


class CredentialFieldRead(BaseModel):
    """One input a connector needs. Describes the field, never a stored value."""

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


class CompanyCreateResult(CompanyRead):
    """What `POST /companies` returns: the company plus the integration it got.

    Extends `CompanyRead` rather than nesting it, so a client reading `.id` off
    the create response keeps working.
    """

    integration: ErpIntegrationRead


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
    # How many of this group's rows had no base amount and were therefore left
    # out of the totals. Non-zero only on a base-mode row whose `currency` is
    # null: that row *is* the unconverted bucket, reported as its own visible
    # line rather than folded into a total it does not belong in.
    unconverted_count: int = 0


class EntryAccountRow(BaseModel):
    erp_account_id: str
    erp_account_code: str
    erp_account_name: str
    currency: str | None = None
    debit_total: Decimal
    credit_total: Decimal
    net: Decimal
    count: int
    # How many of this group's rows had no base amount and were therefore left
    # out of the totals. Non-zero only on a base-mode row whose `currency` is
    # null: that row *is* the unconverted bucket, reported as its own visible
    # line rather than folded into a total it does not belong in.
    unconverted_count: int = 0


class CategorySpendRow(BaseModel):
    level_2: str | None = None
    level_3: str | None = None
    currency: str | None = None
    amount_total: Decimal
    count: int
    # How many of this group's rows had no base amount and were therefore left
    # out of the totals. Non-zero only on a base-mode row whose `currency` is
    # null: that row *is* the unconverted bucket, reported as its own visible
    # line rather than folded into a total it does not belong in.
    unconverted_count: int = 0


class VendorSpendRow(BaseModel):
    vendor_id: str
    vendor_name: str
    currency: str | None = None
    amount_total: Decimal
    count: int
    # How many of this group's rows had no base amount and were therefore left
    # out of the totals. Non-zero only on a base-mode row whose `currency` is
    # null: that row *is* the unconverted bucket, reported as its own visible
    # line rather than folded into a total it does not belong in.
    unconverted_count: int = 0
