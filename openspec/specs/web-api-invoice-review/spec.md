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

The API SHALL provide `GET /api/v1/invoice-lines` returning invoice lines scoped to the caller's organization, with optional `status` and `company_id` filters and `page`/`page_size` pagination. This is the primary data-table surface for reviewing raw, uncategorized line items.

#### Scenario: Review pending line items

- **WHEN** a caller requests `GET /api/v1/invoice-lines?status=pending`
- **THEN** only pending lines under the caller's organization are returned, paginated and deterministically ordered

#### Scenario: Empty result for a tenant with no data

- **WHEN** an authenticated caller whose organization has no invoice lines makes the request
- **THEN** the API responds `200 OK` with an empty page and `total = 0`

