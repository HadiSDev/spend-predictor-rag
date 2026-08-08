## ADDED Requirements

### Requirement: The runner converts amounts into the company's base currency as it persists

While persisting invoices, invoice lines and entries, the runner SHALL convert
each row's monetary amounts into the company's `base_currency`, using the rate in
force on that row's own transaction date, and SHALL write the converted amounts,
the rate, and the rate date onto the row.

The company's base currency SHALL be read from the `Company` row the integration
belongs to. The runner SHALL NOT set, infer, or modify a company's base currency
— it is a customer setting, like `sync_enabled` and `with_vat`.

#### Scenario: A synced entry lands converted

- **WHEN** the runner persists a EUR entry for a DKK-based company and the rate
  for its accounting date is available
- **THEN** the row is written with its EUR amounts, its DKK base amounts, the
  rate and the rate date

#### Scenario: The runner never sets the base currency

- **WHEN** a sync runs for a company
- **THEN** the company's `base_currency` is left exactly as the customer set it

### Requirement: Rate lookups are shared across an integration's run

Within one run, a rate for a given currency and date SHALL be resolved at most
once and reused for every row that needs it, on top of the persistent rate
cache. A sync over thousands of rows spanning a date range SHALL make at most one
external rate request per distinct date not already cached.

#### Scenario: A wide sync does not fan out requests

- **WHEN** the runner persists 5,000 entries spanning 90 accounting dates
- **THEN** at most 90 external rate requests are made, and none for a date
  already in the cache

### Requirement: A rate failure never fails an integration's sync

An FX failure SHALL NOT fail an integration's sync and SHALL NOT abort
persistence — whether the rate provider is disabled, unreachable, timing out, or
missing a currency. The affected rows SHALL be persisted unconverted, the
condition SHALL be logged, and the run SHALL continue.

Unlike an ERP fetch failure — which means there is no data to store — an FX
failure still leaves the ledger data correct and complete. The integration's
watermark SHALL therefore still advance, and the missing conversions SHALL be
fillable later by a recompute.

#### Scenario: The rate provider is down mid-sync

- **WHEN** the rate provider times out while entries are being persisted
- **THEN** the entries are still written with their posted amounts, their base
  fields are null, the integration is not marked failed, and the run continues to
  the next integration

#### Scenario: Ledger data is not held hostage to FX

- **WHEN** an integration's fetch succeeded but every conversion failed
- **THEN** the integration's sync is reported successful and its watermark
  advances

#### Scenario: A later recompute fills the gap

- **WHEN** a recompute is run after the provider recovers
- **THEN** the previously unconverted rows are converted at their own historical
  rates, without re-fetching the ERP

### Requirement: Re-syncing does not re-convert already-converted rows

A re-sync SHALL skip conversion for any row that already carries a rate and
whose stored base currency matches its company's current one, leaving its base
amount, rate, and rate date untouched and issuing no rate lookup for it.

#### Scenario: The second run is idempotent

- **WHEN** the runner syncs the same source data twice
- **THEN** the second run issues no rate lookups for already-converted rows and
  their stored base amounts are unchanged
