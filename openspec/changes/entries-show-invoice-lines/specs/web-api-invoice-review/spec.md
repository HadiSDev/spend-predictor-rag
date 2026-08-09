## MODIFIED Requirements

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

## ADDED Requirements

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
