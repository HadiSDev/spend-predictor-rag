## MODIFIED Requirements

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

## ADDED Requirements

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
