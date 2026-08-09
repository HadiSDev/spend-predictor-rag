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

Every monetary aggregate SHALL group by a currency column and SHALL NOT sum
amounts of different currencies into a single figure. Sums over rows with no
amount SHALL be reported as `0`, not null.

Which currency column is grouped on depends on the request's currency mode:

- In **base** mode the grouping column is the stored `base_currency`, so a
  company whose rows are all converted yields one row per dimension, in the
  customer's own currency.
- In **original** mode the grouping column is the as-posted `currency`, so a
  dimension with values in multiple posted currencies produces one row per
  (dimension value, currency), exactly as before.

In both modes, a row's `currency` field SHALL state which currency the reported
amounts are in, and figures in different currencies SHALL NEVER be added
together.

#### Scenario: Mixed currencies are not combined

- **WHEN** a company has entries in DKK and EUR for the same entry type and the
  request asks for original mode
- **THEN** the summary returns a separate row per currency

#### Scenario: Base mode collapses posted currencies into one figure

- **WHEN** a DKK-based company has entries posted in DKK and EUR for the same
  entry type, all converted
- **THEN** the summary returns one row with `currency: "DKK"` whose totals
  include both

#### Scenario: A mid-recompute company is not silently merged

- **WHEN** some of a company's rows still carry a previous base currency
- **THEN** base mode returns one row per distinct base currency rather than
  summing them together

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

### Requirement: Reports are returned in the company's base currency by default

Every `/api/v1/reports/*` endpoint SHALL accept `currency_mode` with the values
`base` and `original`, defaulting to `base`.

- `base` SHALL aggregate the stored base-currency amounts.
- `original` SHALL aggregate the as-posted amounts and SHALL preserve the
  endpoints' pre-existing behaviour unchanged.
- An unrecognised value SHALL be rejected with `422 Unprocessable Entity`.

#### Scenario: The default is the customer's currency

- **WHEN** a client requests a report without `currency_mode`
- **THEN** the amounts returned are base-currency amounts

#### Scenario: Original mode is unchanged

- **WHEN** a client requests `currency_mode=original`
- **THEN** the response is identical to what the endpoint returned before base
  currency existed

#### Scenario: An unknown mode is rejected

- **WHEN** a client requests `currency_mode=usd`
- **THEN** the API responds `422 Unprocessable Entity`

### Requirement: Amounts that could not be converted are counted, never dropped

In base mode, rows whose base amount is null SHALL NOT have their as-posted
amounts folded into a base-currency total. Because such rows have no base
currency, they SHALL form their own group — one row per dimension with a null
`currency`, zero totals, and an `unconverted_count` giving how many rows it
covers. Every aggregate row SHALL carry `unconverted_count`, which SHALL be `0`
on any group that has a currency and in `original` mode, where nothing is
excluded.

An aggregate whose contributing rows are entirely unconverted SHALL still be
returned — as that null-currency row — rather than omitted, so missing money is
visible rather than invisible.

#### Scenario: Unconverted spend is visible

- **WHEN** four of a company's twenty invoices could not be converted
- **THEN** the base-mode report totals the sixteen converted invoices in one row
  and returns a further null-currency row with `unconverted_count: 4`

#### Scenario: Unconverted money is never added to a base total

- **WHEN** a GBP posting has no base amount and the company reports in DKK
- **THEN** its posted amount is absent from the DKK total rather than counted as
  though it were DKK

#### Scenario: A fully unconverted dimension still appears

- **WHEN** every row for a category is unconverted
- **THEN** the category is returned with a null `currency`, a `0` total and its
  full `unconverted_count`, not omitted from the response

#### Scenario: A converted company reports no gap

- **WHEN** every contributing row is converted
- **THEN** `unconverted_count` is `0` on every row



