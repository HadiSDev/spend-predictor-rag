## ADDED Requirements

### Requirement: A company declares one base currency

Every `Company` SHALL declare a `base_currency`: a single ISO 4217 alphabetic
code that all of that company's monetary figures are presented in. It SHALL be
set when the company is created and SHALL be changeable afterwards by an
authorized caller. It SHALL NOT be inferred from `country_code` at runtime.

Codes SHALL be validated as three uppercase letters and stored uppercased; a
malformed code SHALL be rejected rather than stored.

#### Scenario: A company is created with a base currency

- **WHEN** a company is created with `base_currency: "DKK"`
- **THEN** the stored company reports `DKK`, and every figure derived for that
  company is expressed in `DKK`

#### Scenario: A malformed code is rejected

- **WHEN** a caller supplies `base_currency: "kroner"`
- **THEN** the request is rejected and no company is created or updated

#### Scenario: Two companies in one organization may differ

- **WHEN** an organization owns a Danish company and an Irish company
- **THEN** each may declare its own base currency, and neither inherits the
  other's

### Requirement: Conversion uses the rate in force on the transaction's own date

A monetary row SHALL be converted at the reference rate of **its own
transaction date**, never at the current date's rate.

- An `Invoice` SHALL use its `invoice_date`.
- An `InvoiceLine` SHALL use its invoice's `invoice_date`; a line has no date of
  its own and SHALL NOT be dated independently.
- An `ErpEntry` SHALL use its `accounting_date`.

Once written, a converted amount SHALL NOT change because time passed.

#### Scenario: An old invoice keeps its own rate

- **WHEN** an invoice dated 2024-03-11 in USD is converted for a EUR-based
  company
- **THEN** the 2024-03-11 rate is used, and the stored base amount is unchanged
  when the same invoice is read in 2026

#### Scenario: A line follows its invoice's date

- **WHEN** an invoice line is converted
- **THEN** the rate date used is its invoice's `invoice_date`, not the line's
  creation date

#### Scenario: Today's rate is never substituted

- **WHEN** the rate for a transaction's date cannot be obtained
- **THEN** the row is left unconverted rather than converted at the current rate

### Requirement: Daily reference rates are fetched once and cached against EUR

The system SHALL maintain a cache of daily reference rates keyed by
`(quote_currency, rate_date)`, each rate expressing units of the quote currency
per 1 EUR, sourced from the European Central Bank's published reference rates.

- A `(quote_currency, rate_date)` pair SHALL be fetched from the external
  provider at most once; subsequent lookups SHALL be served from the cache.
- A rate between any two currencies SHALL be derived from the cached EUR rates
  as `rate(A→B) = rate(EUR→B) / rate(EUR→A)`, with `rate(EUR→EUR) = 1`. Pairwise
  rates SHALL NOT be cached separately.
- Each cached row SHALL record which source produced it and when it was
  fetched.

#### Scenario: A repeated date is not re-fetched

- **WHEN** two hundred entries share one accounting date
- **THEN** the external provider is called at most once for that date, and the
  remaining lookups are served from the cache

#### Scenario: A cross-rate is derived, not fetched

- **WHEN** a DKK amount is converted for a SEK-based company
- **THEN** the EUR→DKK and EUR→SEK rates for that date are used to derive the
  DKK→SEK rate, and no DKK-based request is made

#### Scenario: Cached rates survive provider downtime

- **WHEN** the external provider is unreachable and the needed rate is already
  cached
- **THEN** conversion succeeds from the cache

### Requirement: Non-publication dates resolve backwards to the last published rate

The system SHALL resolve a date with no published rate backwards, to the most
recent **prior** publication, and SHALL record that resolved publication date as
the row's rate date. Reference rates are published only on business days, so
weekends and holidays have none of their own. A later publication SHALL NOT be
used.

The resolved rate SHALL also be cached under the originally requested date, so
the same weekend date is not re-requested.

#### Scenario: A Saturday transaction uses Friday's rate

- **WHEN** an entry is dated on a Saturday
- **THEN** the preceding Friday's published rate is used, and the row's stored
  rate date is that Friday

#### Scenario: The resolved date is visible

- **WHEN** a row was converted using a prior day's publication
- **THEN** the stored rate date is the publication date actually used, not the
  transaction date

#### Scenario: A future rate is never used

- **WHEN** a rate is missing for a date and a later publication exists
- **THEN** the later rate is not used

### Requirement: Converted amounts are stored beside the originals with the rate used

Conversion SHALL be materialized on the row at write time. Each converted row
SHALL store its `base_currency`, the converted amount(s), the `fx_rate` applied,
and the `fx_rate_date` that rate was published for.

- The as-posted `currency` and amount columns SHALL NOT be overwritten,
  recalculated, or removed. They are the evidence the conversion is derived
  from.
- `fx_rate` SHALL express **units of base currency per 1 unit of the posted
  currency**, such that `base_amount = amount × fx_rate`.
- Each amount on a row SHALL be converted from its own source amount and SHALL
  NOT be derived from another converted amount.
- Base amounts SHALL be rounded half-up to the same scale as the money columns
  they mirror.
- A row already posted in the base currency SHALL still be marked converted,
  with `fx_rate` = 1 and its transaction date as the rate date, so
  "unconverted" is a single null check rather than a currency comparison.

#### Scenario: Original and converted coexist

- **WHEN** a USD invoice is converted for a DKK-based company
- **THEN** the row reports both the original USD total and the DKK total, plus
  the rate and rate date used

#### Scenario: A stored figure is reproducible

- **WHEN** a stored base amount is recomputed from the stored original amount and
  the stored rate
- **THEN** the result equals the stored base amount

#### Scenario: A same-currency row is marked converted

- **WHEN** a DKK entry belongs to a DKK-based company
- **THEN** its base amount equals its original amount with `fx_rate` = 1, and it
  does not count as unconverted

#### Scenario: Debit and credit convert independently

- **WHEN** an entry carries both a debit and a credit amount
- **THEN** each is converted from its own value at the same rate

### Requirement: A row that cannot be converted is stored unconverted, never guessed

A row SHALL be persisted with its base-currency fields left empty, and its
original values intact, when its transaction date is missing, its posted currency
is missing or not covered by the rate source, or no rate can be obtained. The
system SHALL NOT fall back to the current date's rate, to a rate for a different
currency, or to treating the amount as if it were already in the base currency.

Unconverted rows SHALL remain fully readable and SHALL be identifiable as
unconverted by consumers.

#### Scenario: A dateless entry is not converted

- **WHEN** an entry has no `accounting_date`
- **THEN** it is stored with no base amount and no rate, and its original amount
  is unchanged

#### Scenario: An uncovered currency is not converted

- **WHEN** an invoice is posted in a currency the rate source does not publish
- **THEN** it is stored unconverted rather than converted through a substitute
  currency

#### Scenario: An unconverted row is still readable

- **WHEN** a client reads an unconverted entry
- **THEN** the entry is returned with its original amount and currency, and its
  base fields are empty rather than the request failing

### Requirement: Conversion is idempotent across repeated runs

Conversion SHALL be skipped for a row whose stored conversion is already the one
that would be written: its stored base currency matches its company's, and its
stored base amounts are still **reproducible** from its posted amounts at its
stored rate. For such a row no rate SHALL be re-fetched and the stored base
amount, rate, and rate date SHALL NOT change.

- Reproducibility SHALL be the test, not the mere presence of a rate. Rows are
  upserted in place under a deterministic id, so a row's *posted* amounts can
  change while it still carries a rate that was correct for the previous ones.
  Treating a stored rate as proof of a current conversion freezes the earlier
  posting's base amounts onto the new one — which then reads as a figure from an
  unrelated row, and with the sign inverted when the earlier posting used the
  other side of the ledger.
- A row whose base amounts no longer reproduce SHALL be reconverted at the rate
  for its current date, exactly as an unconverted row would be.
- The test SHALL remain cheap enough not to reintroduce a rate lookup for a row
  that has genuinely not changed: it is arithmetic against the stored rate.

#### Scenario: A re-sync does not churn unchanged rows

- **WHEN** the sync runs twice over the same source data
- **THEN** the second run makes no rate requests for already-converted rows and
  leaves their base amounts byte-identical

#### Scenario: A changed posted amount is reconverted

- **WHEN** a row that already carries a rate is re-posted with a different
  amount
- **THEN** its base amounts are recomputed from the new posted amounts rather
  than left at the previous conversion

#### Scenario: A posting that swaps ledger sides keeps no stale side

- **WHEN** a row that was converted with a credit amount is re-posted as a debit
- **THEN** its base debit is written and its base credit is cleared, so no
  amount survives on the side the posting no longer uses

#### Scenario: A stale base currency is recognised

- **WHEN** a row's stored base currency no longer matches its company's
- **THEN** the row is treated as needing recomputation

### Requirement: Stored conversions can be recomputed on demand

The system SHALL provide a way to recompute a company's stored base amounts —
used after the company changes its base currency and after a rate correction.
Recomputation SHALL rewrite base amounts, rates and rate dates for that
company's rows, SHALL leave the original amounts and currencies untouched, and
SHALL report how many rows were converted, left unconverted, and left unchanged.

Changing a company's base currency SHALL NOT rewrite historical rows inline as
part of that request.

#### Scenario: Switching base currency then recomputing

- **WHEN** a company switches from `DKK` to `EUR` and a recompute is run
- **THEN** its rows are rewritten with EUR base amounts at each row's own
  historical rate, and the original DKK/USD/… amounts are unchanged

#### Scenario: A base-currency change is not an inline rewrite

- **WHEN** the base currency is changed
- **THEN** the request completes without rewriting the company's historical
  rows, and those rows remain readable in the meantime

#### Scenario: Recompute reports its outcome

- **WHEN** a recompute finishes
- **THEN** it reports counts of converted, unconverted, and unchanged rows

### Requirement: The rate source is configurable, off by default, and fails soft

The external rate provider SHALL be reachable through a single narrow seam so it
can be substituted in tests without network access, SHALL be disabled by default
so that no test or offline run makes an outbound request, and SHALL be
configurable by environment (endpoint, enable flag, request timeout).

A provider error, timeout, or disabled provider SHALL degrade to leaving rows
unconverted. It SHALL NOT raise out of the persistence path and SHALL NOT cause
ingestion of financial data to fail.

#### Scenario: Tests make no network calls

- **WHEN** the test suite runs with the default configuration
- **THEN** no outbound rate request is made, and rows are stored unconverted

#### Scenario: A provider outage does not lose data

- **WHEN** the provider times out during ingestion
- **THEN** the rows are still persisted with their original amounts, marked
  unconverted, and the failure is logged rather than raised

#### Scenario: Enabling the provider converts subsequent work

- **WHEN** the provider is enabled and ingestion runs again
- **THEN** rates are fetched and cached, and newly written rows carry base
  amounts
