# sync-pipeline-orchestration Specification

## Purpose
TBD - created by archiving change sync-runner-reads-integrations. Update Purpose after archive.
## Requirements
### Requirement: The sync runner discovers its work from the database

The sync runner SHALL determine what to sync by querying the database for every `ErpIntegration` whose `disconnected_at` is null, and SHALL NOT accept, infer, or create the tenant it operates on.

- For each such integration the runner SHALL take `company_id` and `erp_type`
  from the integration row itself.
- The runner SHALL NOT create an `Organization`, `Company`, or `ErpIntegration`
  under any circumstances. Those are created through the customer-facing API.
- A disconnected integration SHALL be skipped, and reconnecting it SHALL be
  sufficient to include it again with no code or configuration change.
- The work list SHALL NOT be filtered on the company's active state; company
  deactivation and ERP polling are separate concerns.
- When no connected integration exists, the run SHALL succeed with an empty
  result and SHALL say so explicitly, rather than reporting a failure or an
  empty summary that reads like one.

#### Scenario: A company created through the API is synced with no code change

- **WHEN** a company and its ERP integration are created through
  `POST /api/v1/companies` and the sync runner is then run
- **THEN** that integration is synced, and its entries belong to that company and
  its organization

#### Scenario: The runner never invents a tenant

- **WHEN** the sync runner is run against a database with no connected
  integrations
- **THEN** no `Organization`, `Company`, or `ErpIntegration` row is created, and
  the run reports that there is nothing to sync

#### Scenario: A disconnected integration is skipped

- **WHEN** an integration has been disconnected and the runner is run
- **THEN** it is not synced, and reconnecting it is enough for the next run to
  include it

#### Scenario: Every connected integration is covered in one run

- **WHEN** several companies each have a connected integration
- **THEN** one run syncs all of them, each into its own company

### Requirement: Connector credentials come from the integration's stored credential

The runner SHALL build each connector's configuration by decrypting that integration's `ErpCredential`, and SHALL NOT accept credentials as command-line arguments or environment-specific constants.

- When an integration has no `ErpCredential` row, the runner SHALL pass an empty
  configuration so the connector falls back to its declared field defaults. This
  is the normal case for a connector whose fields all have defaults, and SHALL
  NOT be treated as an error.
- A credential that cannot be decrypted SHALL fail only that integration, and
  the reported error SHALL name the environment variable required to decrypt it.

#### Scenario: Stored credentials reach the connector

- **WHEN** an integration has stored credentials and the runner syncs it
- **THEN** the connector is constructed with those decrypted values

#### Scenario: No stored credentials means connector defaults

- **WHEN** an integration has no credential row because its connector's fields
  all have defaults
- **THEN** the sync proceeds using those defaults rather than failing

#### Scenario: An undecryptable credential does not stop the run

- **WHEN** one integration's credentials cannot be decrypted and another
  integration is connected
- **THEN** the first is reported as failed with the missing key named, and the
  second is still synced

### Requirement: A failing integration does not stop the others

Each integration SHALL be synced independently. A failure — unreachable ERP, bad credentials, or an error mid-pipeline — SHALL be recorded on that integration's `SyncState` and SHALL NOT prevent the remaining integrations from being synced.

- Reaching the ERP SHALL be attempted per integration rather than as a
  precondition of the whole run.
- The process SHALL exit non-zero when any integration failed, so a scheduler
  still observes the failure.
- Data already committed for an earlier integration SHALL NOT be rolled back by a
  later integration's failure.

#### Scenario: One unreachable ERP

- **WHEN** two integrations are connected and the first one's ERP is unreachable
- **THEN** the first is recorded as errored on its own `SyncState`, the second is
  synced normally, and the process exits non-zero

#### Scenario: An earlier tenant's data survives a later failure

- **WHEN** the first integration syncs successfully and a later one raises
- **THEN** the first integration's persisted rows remain committed

### Requirement: Each integration syncs from its own watermark

The runner SHALL resolve the incremental `since` date per integration from that integration's `SyncState.last_invoice_date`, so each one continues from its own progress rather than from a single value shared across tenants.

- An explicitly supplied `since` SHALL override the stored watermark for every
  integration in that run, for backfills.
- An integration with no recorded watermark SHALL perform a full fetch.
- Each integration's watermark SHALL be advanced on a successful sync, and an
  errored sync SHALL NOT advance it.

#### Scenario: A second run fetches incrementally

- **WHEN** an integration has synced once and is run again with no explicit
  `since`
- **THEN** the fetch starts from that integration's own recorded watermark

#### Scenario: Two integrations at different points

- **WHEN** two integrations have different recorded watermarks and both are
  synced in one run
- **THEN** each fetches from its own, not from a shared value

#### Scenario: An explicit backfill overrides the watermark

- **WHEN** the runner is given an explicit `since`
- **THEN** every integration in that run fetches from that date regardless of
  its stored watermark

#### Scenario: A failed sync does not advance the watermark

- **WHEN** an integration's sync raises partway through
- **THEN** its `last_invoice_date` is unchanged and its state records the error

### Requirement: A single integration may be selected, but never named into existence

The runner SHALL accept an optional integration identifier that narrows the discovered work list to that one integration, for re-running a single failed sync.

- The identifier SHALL only filter the set the database produced. An identifier
  that matches no connected integration SHALL be an error, and SHALL NOT cause
  anything to be created.
- No option SHALL exist that names an organization, a company, or a connector
  type as the thing to sync.

#### Scenario: One integration is re-run

- **WHEN** the runner is given the identifier of one connected integration
- **THEN** only that integration is synced and the others are left untouched

#### Scenario: An unknown identifier is rejected

- **WHEN** the runner is given an identifier that matches no connected
  integration
- **THEN** the run fails with an error and creates nothing

### Requirement: The run reports per integration

The run's result SHALL be keyed by integration, since one run covers several tenants and a single flat summary can no longer describe it.

- Each entry SHALL identify its company and connector type, state whether that
  integration succeeded or failed, and carry the counts the previous summary
  reported (vendors, invoices, lines, entries, accounts, categorization).
- A failed integration's entry SHALL carry its error message.

#### Scenario: A multi-integration run is reported per integration

- **WHEN** a run covers two integrations, one succeeding and one failing
- **THEN** the result contains an entry for each, the first with its counts and
  the second with its error

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

### Requirement: Rate lookups are shared across a run

Within one run, a rate for a given currency and date SHALL be resolved at most
once and reused for every row that needs it, on top of the persistent rate
cache. The memo SHALL be shared across the run's integrations, so a date two
integrations both need costs one lookup. A sync over thousands of rows spanning
a date range SHALL make at most one external rate request per distinct date not
already cached.

#### Scenario: A wide sync does not fan out requests

- **WHEN** the runner persists 5,000 entries spanning 90 accounting dates
- **THEN** at most 90 external rate requests are made, and none for a date
  already in the cache

#### Scenario: Two integrations share one lookup

- **WHEN** two integrations in the same run both need the rate for one date
- **THEN** that rate is resolved once and reused for both

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

### Requirement: Re-syncing does not re-convert rows that have not changed

A re-sync SHALL skip conversion for a row whose stored base currency matches its
company's current one **and** whose stored base amounts still reproduce from its
posted amounts at its stored rate, leaving its base amount, rate, and rate date
untouched and issuing no rate lookup for it.

- The runner rewrites a row's posted amounts in place on every run, so "carries
  a rate" is not evidence that the stored conversion belongs to the amounts now
  on the row. A row whose posted amounts changed SHALL be reconverted.

#### Scenario: The second run is idempotent

- **WHEN** the runner syncs the same source data twice
- **THEN** the second run issues no rate lookups for already-converted rows and
  their stored base amounts are unchanged

#### Scenario: A re-posted amount is reconverted on the next sync

- **WHEN** the ERP re-posts an entry under the same id with a different amount
- **THEN** the next sync rewrites that entry's base amounts to match the new
  posted amounts



