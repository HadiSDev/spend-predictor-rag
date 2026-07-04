# web-api-reporting Specification

## Purpose
TBD - created by archiving change web-api-reporting. Update Purpose after archive.
## Requirements
### Requirement: Reporting endpoints are tenant-scoped and read-only

The web API SHALL expose read-only aggregate reporting endpoints under
`/api/v1/reports/` available to any authenticated user of the organization. Each
endpoint SHALL scope results to the caller's companies, SHALL accept an optional
`company_id` validated against the caller's scope, and SHALL never aggregate
data outside the caller's organization.

#### Scenario: Aggregates are org-scoped

- **WHEN** a user requests a report
- **THEN** only their organization's companies' data is aggregated

#### Scenario: Foreign company filter is rejected

- **WHEN** a user passes a `company_id` that is not in their scope
- **THEN** the API responds `404 Not Found`

#### Scenario: Empty scope yields empty rows

- **WHEN** a user with no companies requests a report
- **THEN** the response contains no rows (not an error)

### Requirement: Monetary aggregates are grouped by currency

Every monetary aggregate SHALL group by `currency` and SHALL NOT sum amounts of
different currencies into a single figure. A dimension with values in multiple
currencies SHALL produce one row per (dimension value, currency). Sums over rows
with no amount SHALL be reported as `0`, not null.

#### Scenario: Mixed currencies are not combined

- **WHEN** a company has entries in DKK and EUR for the same entry type
- **THEN** the summary returns a separate row per currency

### Requirement: Entry ledger summaries are entry-based

The API SHALL provide `GET /reports/entries-summary` returning, per
`(entry_type, currency)`, the sum of debit amounts, the sum of credit amounts,
their net, and the entry count; and `GET /reports/entries-by-account` returning
the same aggregates per ERP account (id, code, name) and currency. Both SHALL
accept optional `entry_type` and `from`/`to` filters applied to
`accounting_date`.

#### Scenario: Entries summarized by type

- **WHEN** a caller requests the entries summary
- **THEN** each row gives an entry type, currency, summed debits and credits,
  their net, and a count

#### Scenario: Date range filters on the accounting date

- **WHEN** a caller passes `from`/`to`
- **THEN** only entries whose `accounting_date` falls in the range are aggregated

### Requirement: Category spend comes from categorized invoice lines

The API SHALL provide `GET /reports/spend-by-category` returning, per spend-tree
level and currency, the sum of invoice-line amounts and the line count, computed
only from lines whose status is `ai_categorized` or `verified`. A `level`
parameter SHALL select `level_2` granularity (default) or `level_2`+`level_3`.

#### Scenario: Only categorized lines count

- **WHEN** spend-by-category is requested
- **THEN** uncategorized and ai_failed lines are excluded from the totals

#### Scenario: Grouping granularity is selectable

- **WHEN** the caller requests `level=level_3`
- **THEN** rows are grouped by both `level_2` and `level_3`

### Requirement: Vendor spend is invoice-based

The API SHALL provide `GET /reports/spend-by-vendor` returning, per vendor and
currency, the sum of invoice totals and the invoice count, with the vendor's
name included. It SHALL accept an optional `from`/`to` filter on the invoice
date.

#### Scenario: Spend rolled up per vendor

- **WHEN** spend-by-vendor is requested
- **THEN** each row identifies a vendor (id + name), a currency, the summed
  invoice totals, and an invoice count

