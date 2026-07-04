## ADDED Requirements

### Requirement: ErpEntry records the accounting date

`ErpEntry` SHALL record the ledger posting date in a column named
`accounting_date` (nullable `date`). This is the entry's accounting/posting date
and the axis used for period-based reporting. The entry SHALL NOT expose an
ambiguous `entry_date`.

#### Scenario: Posting date is named accounting_date

- **WHEN** an entry is persisted from ERP data
- **THEN** its posting date is stored in `accounting_date`, and no `entry_date`
  column exists on `erp_entries`

#### Scenario: Reporting aggregates on the accounting date

- **WHEN** entries are aggregated over a date range
- **THEN** the range is applied to `accounting_date`

### Requirement: ErpEntry integration is derived through its account

`ErpEntry` SHALL NOT store a direct `erp_integration_id`. An entry's ERP
integration SHALL be reached through its account
(`ErpEntry.erp_account_id → ErpAccount.erp_integration_id`); the entry retains
`company_id` for tenant scope. Scoping an integration's entries SHALL join
through `ErpAccount`.

#### Scenario: No direct integration column

- **WHEN** inspecting `erp_entries`
- **THEN** there is no `erp_integration_id` column, and the integration is
  resolved via the entry's account

#### Scenario: Entries scoped to an integration via the account

- **WHEN** the sync selects the entries belonging to a given integration
- **THEN** it joins `ErpEntry` to `ErpAccount` and filters
  `ErpAccount.erp_integration_id`, and re-syncing the same source upserts the
  same entry rows (idempotent)
