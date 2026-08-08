## ADDED Requirements

### Requirement: Invoice and line payloads carry their base-currency conversion

Every invoice and invoice-line payload the API returns SHALL include the row's
`base_currency`, its converted amount(s), the `fx_rate` applied, and the
`fx_rate_date` that rate was published for, alongside the as-posted `currency`
and amounts.

- An invoice SHALL expose base equivalents of `total` and `tax`.
- An invoice line SHALL expose the base equivalent of `amount`.
- All of these SHALL be `null` on an unconverted row, and the as-posted values
  SHALL continue to report exactly what was posted.
- The fields are read-only and additive; no previously returned field changes
  meaning or disappears.

#### Scenario: An invoice reports both figures

- **WHEN** a client fetches a USD invoice belonging to a DKK-based company
- **THEN** the payload carries the USD total and tax, the DKK total and tax, the
  rate applied, and the rate date

#### Scenario: Lines carry their own conversion

- **WHEN** a client lists invoice lines
- **THEN** each line carries its own base amount, rate, and rate date

#### Scenario: An unconverted invoice is still returned

- **WHEN** an invoice has no `invoice_date` and so could not be converted
- **THEN** it is returned with `null` base fields and its posted amounts intact

### Requirement: Line-level base amounts are not asserted to sum to the invoice's

The API SHALL NOT adjust, redistribute, or reconcile base amounts to force a
converted invoice's line base amounts to sum to its own base total, and no
endpoint SHALL reject or flag an invoice on that basis. Each amount is converted
independently from its own posted value, so the two MAY differ by a rounding
remainder.

#### Scenario: A rounding remainder is tolerated

- **WHEN** a converted invoice's line base amounts sum to one minor unit less
  than its base total
- **THEN** both figures are returned unmodified and no error or warning is
  raised
