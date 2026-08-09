## ADDED Requirements

### Requirement: Company carries a base currency

`Company` SHALL carry a non-null `base_currency` holding an ISO 4217 alphabetic
code. It is a customer setting, not ERP metadata: no connector, sync, or
refresh SHALL overwrite it.

Existing companies SHALL be given a value when the column is introduced, derived
from the currency their data is most often posted in and falling back to `EUR`
when they have no posted amounts.

#### Scenario: Base currency is required on the row

- **WHEN** a `Company` is persisted
- **THEN** it has a `base_currency`, and a company without one cannot be stored

#### Scenario: A sync never rewrites it

- **WHEN** an ERP sync or account refresh runs for the company
- **THEN** `base_currency` is left exactly as the customer set it

### Requirement: FxRate stores one daily reference rate per currency and date

A new `FxRate` entity SHALL store the daily reference rate for one currency on
one date, expressed as units of that currency per 1 EUR, together with the
source that produced it and when it was fetched. `(quote_currency, rate_date)`
SHALL be unique.

`FxRate` is reference data, not tenant data: it SHALL carry no
`organization_id` and no `company_id`, and one row SHALL serve every company.

#### Scenario: A rate is stored once per currency and date

- **WHEN** the same currency and date are looked up by two different companies
- **THEN** one `FxRate` row serves both, and no duplicate row is written

#### Scenario: Rates are not tenant-scoped

- **WHEN** an `FxRate` row is inspected
- **THEN** it references no organization or company

### Requirement: Money-bearing rows carry their base-currency conversion

`Invoice`, `InvoiceLine` and `ErpEntry` SHALL each carry, alongside their
as-posted currency and amounts, a nullable `base_currency`, nullable base
amount column(s) mirroring their money columns, a nullable `fx_rate`, and a
nullable `fx_rate_date`.

- `Invoice` SHALL mirror `total` and `tax`.
- `InvoiceLine` SHALL mirror `amount`.
- `ErpEntry` SHALL mirror `debit_amount` and `credit_amount`.
- Base amounts SHALL use the same numeric scale as the columns they mirror;
  `fx_rate` SHALL be stored with enough precision that a stored base amount can
  be re-derived from the original amount and the rate.
- Null base fields SHALL mean "not converted" — never "converted to zero".
- The existing `currency` and amount columns SHALL retain their meaning: the
  value exactly as the ERP posted it.

#### Scenario: An entry carries both figures

- **WHEN** a converted `ErpEntry` is read
- **THEN** it exposes its posted currency and debit/credit amounts, and its base
  currency, base debit/credit amounts, rate, and rate date

#### Scenario: Unconverted means null, not zero

- **WHEN** a row could not be converted
- **THEN** its base amount columns are null, and no consumer reads them as `0`

#### Scenario: The posted amount is never rewritten

- **WHEN** a row is converted or later recomputed
- **THEN** its `currency` and posted amounts are byte-identical to before
