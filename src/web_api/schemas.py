"""Pydantic response schemas for the web API (wire contract, not ORM)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

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


class IntegrationReplace(IntegrationSpec):
    """Replace a company's ERP connection with a different system.

    Subclasses `IntegrationSpec` rather than re-declaring its fields so the
    credential shape cannot drift from the two paths that already create an
    integration.

    `confirm` acknowledges that the outgoing integration's ledger data stays and
    the new ERP will re-deliver overlapping periods as separate rows. Required
    only when there is such data — see the 409 body.
    """

    confirm: bool = False


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
    # The taxonomy this company categorizes against. The name is resolved
    # server-side so a client can show which tree is in use without a second
    # request — the same reason `ErpEntryRead` resolves its account.
    spend_tree_id: str | None = None
    spend_tree_name: str | None = None


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
    # Omitted means "the organization's copy of the default template", created
    # on the spot if this is its first company. A company is never left without
    # a taxonomy, exactly as it is never left without an ERP connection.
    spend_tree_id: str | None = None


class CompanyUpdate(BaseModel):
    """Request body to update a company. All fields optional (partial update)."""

    name: str | None = Field(default=None, min_length=1)
    country_code: str | None = None
    vat_number: str | None = None
    # Changing this does NOT rewrite already-stored converted amounts — an
    # unbounded write has no business inside a PATCH. Rows are rewritten by
    # POST /companies/{id}/recompute-fx (or the backfill CLI).
    base_currency: CurrencyCode | None = None
    # Changing this re-points or clears every categorized line of the company in
    # the same transaction; see `CompanyUpdateResult.stale_lines`.
    spend_tree_id: str | None = None


class CompanyUpdateResult(CompanyRead):
    """What `PATCH /companies` returns: the company plus what the change cost.

    `stale_lines` is how many already-categorized lines were left pointing at
    nothing by a spend-tree change. Returned rather than left for the client to
    discover, because a reassignment's consequence has to be visible at the
    moment it is caused.
    """

    stale_lines: int = 0


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
    # What `quantity` counts ('pcs', 'hours'). Null is the ordinary case — an
    # ERP bill line states no unit — and is never filled with a default.
    unit: str | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    native_account_code: str | None = None
    # Which source produced this line: 'erp' | 'document_ai' | 'entry_fallback'.
    # A stand-in line and an extracted line are identical in every other field,
    # and the difference decides whether the description can be trusted — so it
    # travels with the line rather than being inferred from it.
    origin: str = "erp"
    # Position on the invoice, as its source stated it. Carried so a client can
    # keep the order after a client-side sort, and so the ordering is inspectable
    # rather than an implicit property of the response.
    sequence: int = 0
    # The currency the line was posted in. A line has none of its own — it is
    # its invoice's, and it is what `amount` above is denominated in. Resolved
    # server-side for the same reason `ErpEntryRead` resolves its account: a
    # client would otherwise fetch the invoice to render one row.
    currency: str | None = None
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
    # Set only when the company's tree is four levels deep.
    level_4: str | None = None
    account_code: str | None = None
    account_name: str | None = None
    confidence: Decimal | None = None
    rationale: str | None = None
    # Accepted category assignment (null until it resolves to a real spend category).
    spend_category_id: str | None = None
    # The fields of this line a human has settled — the categorization fields a
    # verify wrote, and any of the descriptive/money fields a correction set.
    verified_fields: list[str] = []
    # True when the line carries a categorization that no longer resolves to a
    # node — the company's tree changed, or the node was deleted. Computed, not
    # stored: nothing to keep in step, and correct after every path that can
    # orphan a pointer. Deliberately server-side: a client cannot know which
    # tree a company is assigned without a second request, and a stale category
    # presented as a settled one is the failure this whole feature exists to
    # prevent. Derived in `_derive_category_stale` below rather than by each
    # router, so the four places that build this payload cannot disagree.
    category_stale: bool = False

    @model_validator(mode="after")
    def _derive_category_stale(self) -> "InvoiceLineRead":
        """A decision with no resolving node is stale.

        The test is "any level recorded", not `level_1` alone: a tree node's path
        always starts at level 1, but lines categorized before spend trees
        existed carry a `level_2` with no `level_1`, and those are exactly the
        lines that most need reviewing. An `ai_failed` line has neither a level
        nor a pointer and is correctly *not* stale — nothing was decided.

        Kept in step with the SQL form of the same predicate in
        `routers/invoice_lines.py` and `spend_trees/reassign.py:count_stale`.
        """
        decided = self.level_1 is not None or self.level_2 is not None
        object.__setattr__(
            self, "category_stale", decided and self.spend_category_id is None
        )
        return self


class InvoiceLineVerify(BaseModel):
    """Verify a line, optionally correcting its category. Omitted fields are kept.

    Any provided field overwrites the AI result before the line is marked
    ``verified``; omitting the body accepts the AI result as-is.
    """

    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    account_code: str | None = None
    account_name: str | None = None
    confidence: Decimal | None = None
    rationale: str | None = None
    # Naming a node is the correct way to correct a category: the server takes
    # the levels from that node's path, so the result always resolves to a real
    # row. Any level values sent alongside are ignored — see the router.
    spend_category_id: str | None = None


class InvoiceLineUpdate(BaseModel):
    """A human's correction of what a line says was bought.

    `extra="forbid"` deliberately: a `spend_category_id` sent here would be
    silently ignored and read to the caller as a category edit that did nothing.
    A category is corrected through `verify`, which resolves it against the
    company's spend tree — the one path that guarantees the stored decision
    points at a real node. `native_account_code` is likewise refused: it is the
    ledger's own statement of where the money was posted, and a value
    contradicting it reconciles against nothing.
    """

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class InvoiceLineCreate(InvoiceLineUpdate):
    """A line a reviewer added by hand, typically splitting a stand-in.

    Carries the same fields a correction does, plus where it sits. Its `origin`
    is not a parameter: a line created here is `human` by construction, and
    letting a caller claim it came from the ERP would make the origin a claim
    rather than a fact.
    """

    # Where on the invoice it belongs. Omitted means "after the last line",
    # which is what appending means; explicit means the reviewer is inserting it
    # into the document's own order.
    sequence: int | None = None


class InvoiceUpdate(BaseModel):
    """Corrections to a parsed invoice header.

    Not gated on provenance: an ERP-posted header is as correctable as an
    extracted one, and what protects the correction from the next sync is the
    row's `verified_fields`, not a refusal to write.

    The three `supplier_*` fields are **invoice-scoped overrides**, never a
    write-through to the `Vendor` row: the vendor catalog is global, so one
    organization correcting a supplier's country would rewrite it for every
    other tenant. Re-pointing `vendor_id` is the other, different correction —
    "this is the wrong supplier" rather than "this supplier's details are wrong
    on this document".
    """

    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    total: Decimal | None = None
    tax: Decimal | None = None
    vendor_id: str | None = None
    supplier_name: str | None = None
    supplier_country_code: str | None = Field(default=None, max_length=2)
    supplier_vat_number: str | None = None


class InvoiceVerify(InvoiceUpdate):
    """Verify an invoice header, optionally correcting it first.

    The same fields `InvoiceUpdate` accepts, and deliberately a separate type
    from it: verification is a distinct auditable action, and an absent body —
    "the parse is right as it stands" — is the single most valuable signal this
    endpoint collects. Folded into `PATCH` as a flag, that case would be
    indistinguishable from an empty correction.
    """


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
    # The voucher's invoice lines — what the Entries page lists when a group is
    # expanded. Carried here rather than fetched per expanded row: the table
    # renders lines on expand, and a request per voucher would make the page's
    # cost a function of how much the user explores.
    #
    # Empty for a voucher with no source invoice (a journal entry, a transfer).
    # That is ordinary, not an error — lines are not universal.
    lines: list[InvoiceLineRead] = []
    # The invoice's document-processing state, so a reader can tell provisional
    # lines from read-the-document ones and see why processing failed. Null when
    # the voucher has no source invoice at all.
    doc_status: str | None = None
    doc_error: str | None = None
    # The voucher's invoice number, both as posted and as read off the scan, so
    # the table can prefer the printed one and still show a disagreement.
    invoice_number: str | None = None
    document_invoice_number: str | None = None


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    vendor_id: str | None = None
    invoice_number: str | None = None
    # The number printed on the scan, beside the as-posted one above rather than
    # over it. The as-posted value is often a fallback identifier (Billy uses the
    # bill id when the customer left the field blank), so the two disagreeing is
    # information, not noise.
    document_invoice_number: str | None = None
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
    # The supplier as this invoice states it: the human's override when one was
    # made, otherwise the linked vendor's value. Resolved server-side for the
    # same reason `ErpEntryRead` resolves its account — the client would
    # otherwise fetch the vendor to render one row — and because the fallback
    # rule must not be reimplemented per client.
    supplier_name: str | None = None
    supplier_country_code: str | None = None
    supplier_vat_number: str | None = None
    # Which of the three above are the human's rather than the catalog's. Sent
    # so a reader can tell a corrected supplier from a catalogued one without
    # fetching the vendor to compare: an override that looks identical to the
    # catalog value is still a human's assertion, and marking it is what lets the
    # UI offer the catalog value back.
    supplier_overrides: list[str] = []
    status: str
    # 'erp' | 'pdf_extraction' — see Invoice.source. Provenance only: it tells a
    # reviewer how much to trust a value and no longer decides whether the value
    # may be corrected. What protects a correction is `verified_fields` below.
    source: str = "erp"
    # The fields a human has settled, and who settled them when. Per field, not
    # per row, so a sync still refreshes everything nobody has spoken for.
    verified_fields: list[str] = []
    verified_at: datetime | None = None
    verified_by: str | None = None
    error_message: str | None = None
    file_id: str | None = None
    # Resolved from the linked File so a client never needs a second lookup to
    # decide whether to render a viewer.
    file_name: str | None = None
    has_document: bool = False
    # Whether the attached document has been turned into lines:
    # 'not_applicable' | 'pending' | 'processing' | 'processed' | 'failed'.
    # Deliberately separate from `status` above, which is the categorization
    # rollup — one says whether we have read the document, the other whether the
    # resulting spend has been categorized.
    doc_status: str = "not_applicable"
    # Readable, because it is shown to the user beside the retrigger action
    # rather than only logged.
    doc_error: str | None = None
    doc_processed_at: datetime | None = None


class InvoiceDetailRead(InvoiceRead):
    lines: list[InvoiceLineRead] = []
    # Do the lines add up to the header? Computed on read, never stored: it is a
    # pure function of the lines and the header, both of which several endpoints
    # can now change, and a stored flag would have to be recomputed at each of
    # them — the same reasoning that keeps `category_stale` computed.
    #
    # The rule is `web_api/reconcile.py`, shared with the document extraction
    # stage, so an extraction accepted as reconciling is never then reported to
    # a reviewer as not reconciling. True when the invoice states no total:
    # nothing to check against is not a mismatch.
    lines_reconciled: bool = True
    # Signed: `sum(lines) − nearest accepted total`, so a reader can see which
    # way it is out. Null when the lines reconcile and null when there is no
    # total. Reported, never enforced — a reviewer part-way through a multi-line
    # correction must not be blocked by their own unfinished work, and the ERP's
    # total may itself be the wrong figure.
    reconciliation_delta: Decimal | None = None


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

    `amount` and `currency` follow the same `currency_mode=base|original` split
    as `VoucherGroupRead` (base by default) and are computed by the very same
    helper (`_voucher_amount` in `erp_entries.py`) — not a client-side
    reimplementation — so a table row's total and the panel opened from that
    row can never disagree.
    """

    voucher_id: str | None = None
    company_id: str
    accounting_date: date | None = None
    # Claimed only when every summed entry agrees — in base mode that means
    # they agree on `base_currency`, so a voucher posted in two currencies but
    # converted to one still reports that one.
    currency: str | None = None
    # Signed net spend: debit - credit over the voucher's *expense* postings
    # only. Not `debit_total - credit_total`, which is zero for any balanced
    # voucher. Null when the voucher moved money without spending any (a
    # payment), or when nothing was summable at all (every posting unconverted
    # in base mode, or the postings disagree on currency in original mode).
    amount: Decimal | None = None
    entry_count: int
    entries: list[ErpEntryRead] = []
    invoice: InvoiceDetailRead | None = None
    document: DocumentRead | None = None


class VoucherAuditRead(AuditLogRead):
    """An audit row with the thing it happened to already named.

    The same reasoning as `ErpEntryRead` resolving its account and vendor: a
    feed of foreign keys would cost the client a lookup per row.
    """

    entity_label: str


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
    """A registered connector type, as offered to a client picker.

    The brand fields are what let a client render a recognisable, branded
    chooser without knowing any connector by name — the catalog is the only
    place a connector's identity is declared. All three are optional, so a
    connector declaring none produces the payload this model always produced.
    """

    erp_type: str
    label: str
    credential_fields: list[CredentialFieldRead] = Field(default_factory=list)
    #: Key for locating vendored artwork client-side. Never a URL: artwork is
    #: bundled, so a catalog entry can't point a client at a third-party host.
    brand_slug: str | None = None
    description: str | None = None
    docs_url: str | None = None


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
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
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


# -- Spend trees -------------------------------------------------------------


class SpendCategoryRead(BaseModel):
    """One node. Carries both its parentage and its materialized path.

    The client needs `parent_id`/`depth` to build the hierarchy and the
    `level_*` path to show a chosen node's full address without walking back up.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    spend_tree_id: str
    parent_id: str | None = None
    depth: int
    name: str
    code: str | None = None
    sort_order: int
    description: str | None = None
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None


class SpendTreeRead(BaseModel):
    """A tree in the list view, with what a manager needs to choose between them."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    max_depth: int
    # "default_template" — the organization's own copy of the platform template —
    # or "custom".
    source: str
    template_version: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    node_count: int = 0
    # Which companies categorize against this tree. Resolved server-side because
    # it is the answer to "can I archive this?", and a client would otherwise
    # have to fetch every company to work it out.
    company_ids: list[str] = Field(default_factory=list)
    company_names: list[str] = Field(default_factory=list)


class SpendTreeDetailRead(SpendTreeRead):
    """One tree with every node, ordered so a client can build it in one pass."""

    nodes: list[SpendCategoryRead] = Field(default_factory=list)


class SpendTreeCreate(BaseModel):
    """Create a tree: empty, or cloned from an existing one.

    `source_tree_id` is what separates the two authoring paths that produce a
    populated tree; CSV import is a second step against an existing tree, since
    a rejected file must leave something behind to retry against.
    """

    name: str = Field(min_length=1)
    # 3 or 4. Validated against the tree's contents in the service, not here:
    # "4 is only allowed on a custom tree" is a rule about the source, not the
    # number.
    max_depth: int = Field(default=3, ge=3, le=4)
    source_tree_id: str | None = None


class SpendTreeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    max_depth: int | None = Field(default=None, ge=3, le=4)


class SpendCategoryCreate(BaseModel):
    name: str = Field(min_length=1)
    parent_id: str | None = None
    code: str | None = None
    description: str | None = None
    sort_order: int | None = None


class SpendCategoryUpdate(BaseModel):
    """Partial update. `parent_id` is only applied when explicitly supplied,
    since `None` is a legitimate value meaning "move to the top level"."""

    name: str | None = Field(default=None, min_length=1)
    parent_id: str | None = None
    code: str | None = None
    description: str | None = None
    sort_order: int | None = None


class SpendTreeImportError(BaseModel):
    """One rejected row, addressed by its line number in the uploaded file."""

    line: int
    message: str


class SpendTreeImportResult(BaseModel):
    """What an import did, or — with `confirm_required` — what it would do."""

    created: int = 0
    updated: int = 0
    removed: int = 0
    # Lines left pointing at nothing because their node was removed.
    stale_lines: int = 0


class SpendTreeDeleteResult(BaseModel):
    """Deleting a node reports what it cost, in lines that now need review."""

    stale_lines: int = 0
