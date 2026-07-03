## ADDED Requirements

### Requirement: List ERP entries with filters and pagination

The API SHALL expose `GET /api/v1/erp-entries` returning a paginated list of `ErpEntry` rows scoped to the caller's tenant, so clients can read raw GL postings.

- Results SHALL be restricted to companies within the caller's scope; a
  non-system-admin SHALL only see entries for their organization's companies, and
  a system admin MAY read across organizations.
- The endpoint SHALL support pagination (`page`, `page_size`) and return a
  `Page`-shaped body (`items`, `page`, `page_size`, `total`).
- The endpoint SHALL support optional filters: `company_id`, `entry_type`,
  `voucher_id`, `source_invoice_id`, and `status`. Filters compose (AND).
- When the caller has no companies in scope, the endpoint SHALL return an empty
  page (not an error).
- The response SHALL NOT include ground-truth (`gt_*`) columns.

#### Scenario: Paginated, tenant-scoped list

- **WHEN** an authenticated member requests `GET /api/v1/erp-entries`
- **THEN** the response contains only entries whose `company_id` is in the
  caller's scope, paginated with a `total` count

#### Scenario: Filter by source invoice

- **WHEN** a client requests `GET /api/v1/erp-entries?source_invoice_id=<id>`
- **THEN** only entries linked to that invoice (and within scope) are returned

#### Scenario: Filter by voucher and entry type

- **WHEN** a client requests `GET /api/v1/erp-entries?voucher_id=V1&entry_type=purchase_invoice`
- **THEN** only entries matching both filters (and within scope) are returned

#### Scenario: No companies in scope yields an empty page

- **WHEN** a caller with no companies in scope lists entries
- **THEN** the response is an empty page with `total` = 0 and HTTP 200

### Requirement: Fetch a single ERP entry

The API SHALL expose `GET /api/v1/erp-entries/{entry_id}` returning one `ErpEntry`, and SHALL return 404 when the entry does not exist or is outside the caller's tenant scope.

- A found entry within scope SHALL be returned as an `ErpEntryRead`.
- An entry that exists but belongs to a company outside the caller's scope SHALL
  return 404 (not 403), so existence is not leaked across tenants.

#### Scenario: Fetch an in-scope entry

- **WHEN** a client requests `GET /api/v1/erp-entries/{id}` for an entry in its scope
- **THEN** the single entry is returned

#### Scenario: Out-of-scope or unknown entry returns 404

- **WHEN** a client requests an entry id that is unknown or belongs to another tenant
- **THEN** the API responds 404 Not Found
