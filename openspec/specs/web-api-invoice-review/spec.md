# web-api-invoice-review Specification

## Purpose
TBD - created by archiving change web-api-clerk-review. Update Purpose after archive.
## Requirements
### Requirement: List the caller's companies

The API SHALL provide `GET /api/v1/companies` returning the companies belonging to the authenticated caller's organization. Each item SHALL include at least `id`, `name`, `country_code`, and `vat_number`.

#### Scenario: Returns only the organization's companies

- **WHEN** an authenticated caller requests `GET /api/v1/companies`
- **THEN** the response lists exactly the companies under the caller's `organization_id`, and none from any other organization

### Requirement: List invoices with status filter and pagination

The API SHALL provide `GET /api/v1/invoices` returning invoices scoped to the caller's organization. It SHALL accept an optional `status` filter (e.g. `pending`), an optional `company_id` filter (which MUST belong to the caller), and `page`/`page_size` pagination parameters. The response SHALL include the page of items and pagination metadata (`page`, `page_size`, `total`). Ordering SHALL be deterministic.

#### Scenario: Filter to raw uncategorized invoices

- **WHEN** a caller requests `GET /api/v1/invoices?status=pending`
- **THEN** only invoices with `status = pending` under the caller's organization are returned, ordered deterministically

#### Scenario: Pagination bounds the result set

- **WHEN** a caller requests a page with `page_size=50`
- **THEN** at most 50 items are returned and the metadata reports the total count and current page

#### Scenario: company_id filter is tenant-checked

- **WHEN** a caller passes a `company_id` that is not in their organization
- **THEN** the API returns `404 Not Found` and no invoices

### Requirement: Fetch one invoice with its lines

The API SHALL provide `GET /api/v1/invoices/{invoice_id}` returning the invoice header and its `InvoiceLine` rows, only when the invoice belongs to the caller's organization. Each line SHALL include the raw fields (`description`, `quantity`, `unit_price`, `amount`, `native_account_code`) and its `status`, plus categorization fields when present.

#### Scenario: Owner fetches invoice detail

- **WHEN** a caller requests an invoice that belongs to their organization
- **THEN** the response includes the invoice header and all of its lines

#### Scenario: Non-owner cannot fetch another tenant's invoice

- **WHEN** a caller requests an `invoice_id` belonging to a different organization
- **THEN** the API responds `404 Not Found`

### Requirement: List invoice lines with filters and pagination

The API SHALL provide `GET /api/v1/invoice-lines` returning invoice lines scoped
to the caller's organization, with optional `status`, `company_id`, `voucher_id`,
`vendor_id`, `origin` and `from`/`to` filters and `page`/`page_size` pagination.
This is the primary data-table surface for reviewing spend at the line level.

- `from`/`to` SHALL bound the line's **invoice date**, since a line has no date
  of its own — the same date the line was converted at, so a filtered period and
  the amounts shown for it agree.
- `vendor_id` SHALL resolve through the line's invoice, which is where the
  supplier lives; a line carries no vendor of its own.
- `voucher_id` SHALL resolve through the postings of the line's invoice, so a
  caller holding a voucher can ask for the lines behind it.
- `origin` SHALL filter on the line's provenance (`erp`, `document_ai`,
  `entry_fallback`), so an operator can find every invoice still standing on its
  postings.
- Filters SHALL compose, and results SHALL be deterministically ordered.
- The listing SHALL be scoped to **active** companies when no `company_id` is
  given, matching every other unfiltered listing.

#### Scenario: Review pending line items

- **WHEN** a caller requests `GET /api/v1/invoice-lines?status=pending`
- **THEN** only pending lines under the caller's organization are returned,
  paginated and deterministically ordered

#### Scenario: Empty result for a tenant with no data

- **WHEN** an authenticated caller whose organization has no invoice lines makes
  the request
- **THEN** the API responds `200 OK` with an empty page and `total = 0`

#### Scenario: Filter by period

- **WHEN** a caller requests `?from=2026-03-01&to=2026-03-31`
- **THEN** only lines whose invoice date falls in March 2026 are returned

#### Scenario: Filter by supplier

- **WHEN** a caller requests `?vendor_id=…`
- **THEN** only lines whose invoice names that supplier are returned

#### Scenario: Filter by voucher

- **WHEN** a caller requests `?voucher_id=…`
- **THEN** only the lines of the invoice that voucher's postings came from are
  returned

#### Scenario: Find invoices still standing on their postings

- **WHEN** a caller requests `?origin=entry_fallback`
- **THEN** only stand-in lines are returned

#### Scenario: Filters compose

- **WHEN** a caller requests `?vendor_id=…&from=2026-03-01&status=ai_categorized`
- **THEN** only lines satisfying all three are returned

### Requirement: Invoice and line payloads carry their base-currency conversion

Every invoice and invoice-line payload the API returns SHALL include the row's
`base_currency`, its converted amount(s), the `fx_rate` applied, and the
`fx_rate_date` that rate was published for, alongside the as-posted `currency`
and amounts.

- An invoice SHALL expose base equivalents of `total` and `tax`.
- An invoice line SHALL expose the base equivalent of `amount`.
- All of these SHALL be `null` on an unconverted row, and the as-posted values
  SHALL continue to report exactly what was posted.
- The fields are read-only and additive; no previously returned field changes
  meaning or disappears.

#### Scenario: An invoice reports both figures

- **WHEN** a client fetches a USD invoice belonging to a DKK-based company
- **THEN** the payload carries the USD total and tax, the DKK total and tax, the
  rate applied, and the rate date

#### Scenario: Lines carry their own conversion

- **WHEN** a client lists invoice lines
- **THEN** each line carries its own base amount, rate, and rate date

#### Scenario: An unconverted invoice is still returned

- **WHEN** an invoice has no `invoice_date` and so could not be converted
- **THEN** it is returned with `null` base fields and its posted amounts intact

### Requirement: Line-level base amounts are not asserted to sum to the invoice's

The API SHALL NOT adjust, redistribute, or reconcile base amounts to force a
converted invoice's line base amounts to sum to its own base total, and no
endpoint SHALL reject or flag an invoice on that basis. Each amount is converted
independently from its own posted value, so the two MAY differ by a rounding
remainder.

#### Scenario: A rounding remainder is tolerated

- **WHEN** a converted invoice's line base amounts sum to one minor unit less
  than its base total
- **THEN** both figures are returned unmodified and no error or warning is
  raised

### Requirement: Line and invoice payloads carry provenance and processing state

`InvoiceLineRead` SHALL carry the line's `origin`, and `InvoiceRead` SHALL carry
`doc_status`, `doc_error` and `doc_processed_at` alongside the existing
`has_document`.

- A client SHALL be able to tell a stand-in line from an extracted one without a
  second request, because the two look identical in every other field and the
  difference decides whether the reader should trust the description.
- `doc_error` SHALL be a human-readable reason, since it is shown to the user
  beside the retrigger action rather than only logged.

#### Scenario: A line states its origin

- **WHEN** a caller reads any invoice line
- **THEN** the payload carries `origin`

#### Scenario: An invoice states why processing failed

- **WHEN** a caller reads an invoice whose extraction failed
- **THEN** the payload carries `doc_status = failed` and a readable `doc_error`

#### Scenario: An invoice with no scan says so plainly

- **WHEN** a caller reads an invoice with no attached document
- **THEN** `has_document` is false, `doc_status` is `not_applicable`, and
  `doc_error` is null



