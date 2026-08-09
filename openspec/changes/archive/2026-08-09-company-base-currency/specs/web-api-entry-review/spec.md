## MODIFIED Requirements

### Requirement: Entry representation carries its account and supplier

`ErpEntryRead` SHALL include the entry's resolved account and supplier alongside their identifiers, so a client can render a posting without resolving foreign keys itself.

- `erp_account_code` and `erp_account_name` SHALL be taken from the entry's
  `erp_account_id`.
- `vendor_id` and `vendor_name` SHALL be taken from the entry's source invoice's
  vendor, and SHALL be `null` when the entry has no source invoice or that
  invoice has no vendor.
- `error_message` SHALL be included, so a failed entry can explain itself in the
  product rather than only in the sync runner's output.
- `erp_account_type` SHALL be included, so a client can show which postings make
  up a voucher's net spend and which are VAT or the counterparty.
- `base_currency`, `base_debit_amount`, `base_credit_amount`, `fx_rate` and
  `fx_rate_date` SHALL be included, so a client can present the entry in the
  company's own currency and explain that figure — the rate used and the date it
  was published for — without a second request. They SHALL be `null` on an
  unconverted entry, and the as-posted `currency`, `debit_amount` and
  `credit_amount` SHALL continue to report exactly what the ERP posted.
- These fields are read-only and additive; no previously returned field changes
  meaning or disappears.

#### Scenario: Account is resolved on every entry

- **WHEN** any endpoint returns an `ErpEntryRead`
- **THEN** the payload includes the account's code and name, not only its id

#### Scenario: Supplier is null when the entry is unlinked

- **WHEN** an entry has no `source_invoice_id`
- **THEN** `vendor_id` and `vendor_name` are `null` rather than absent or errored

#### Scenario: Both figures travel together

- **WHEN** a converted entry posted in EUR is returned for a DKK-based company
- **THEN** the payload carries the EUR amounts and currency, the DKK amounts and
  base currency, the rate applied, and the rate date

#### Scenario: An unconverted entry reports null base fields

- **WHEN** an entry could not be converted
- **THEN** its base fields are `null` and its posted amounts are unchanged

### Requirement: List ERP entries grouped by voucher

The API SHALL expose `GET /api/v1/erp-entries/vouchers` returning a paginated list of voucher groups, each carrying its constituent entries, so a client can present the several postings that make up one spend event as a single unit.

- The endpoint SHALL be tenant-scoped and SHALL accept the same filters as
  `GET /api/v1/erp-entries` (`company_id`, `entry_type`, `status`, `from`, `to`,
  `vendor_id`, `source_invoice_id`), applied to the entries before grouping.
- Pagination (`page`, `page_size`) SHALL be **over groups, not entries**, so a
  voucher's postings are never split across a page boundary and a group's totals
  always reflect all of its entries.
- A group SHALL be identified by `(company_id, voucher_id)`. An entry whose
  `voucher_id` is null SHALL form its own single-entry group with
  `voucher_id: null`, and SHALL NOT be merged with other voucherless entries.
- Each group SHALL report `entry_count`, `amount`, `debit_total`, `credit_total`,
  the latest `accounting_date` among its entries, its distinct `entry_types`, and
  its full `entries` list.
- `amount` SHALL be the group's **net spend**: the sum of `debit - credit` over
  only those entries posted to an expense account. It is signed, so a credit note
  or reversal — which credits the expense account — reports negative spend with no
  special handling. VAT and the payable counterparty are excluded, which is what
  makes it agree with `GET /reports/spend-by-category`.
- `debit_total - credit_total` SHALL NOT be used as the group's amount: a
  balanced voucher nets to zero by construction, so that difference is always
  zero and says nothing.
- When no entry in the group is posted to an expense account — a payment or
  transfer voucher, which moves money without spending it — `amount` SHALL be
  `null` rather than `0`, so "no spend here" is not shown as a zero figure.
- When the connector supplies no account types at all, `amount` SHALL fall back
  to `debit_total`, so the column degrades to the voucher's magnitude instead of
  reading empty for every row.
- The endpoint SHALL accept `currency_mode` with the values `base` and
  `original`, defaulting to `base`. In base mode a group's totals SHALL be summed
  from its entries' base-currency amounts and its `currency` SHALL be the base
  currency; in original mode they SHALL be summed from the as-posted amounts and
  its `currency` SHALL be the posted currency, exactly as before.
- A group's `currency`, `vendor_id`, and `vendor_name` SHALL be reported only
  when every entry in the group agrees; when they disagree the field SHALL be
  `null`. Amounts SHALL NOT be summed across differing currencies. In base mode
  this test applies to the entries' `base_currency`, so a voucher whose postings
  were posted in different currencies but converted to one base currency reports
  that base currency and one combined total.
- In base mode a group SHALL report `unconverted_count`: how many of its entries
  have no base amount. Those entries SHALL be excluded from the group's base
  totals rather than folded in at their posted value. A group whose entries are
  all unconverted SHALL report `null` totals rather than zeros.
- Every entry inside a group SHALL carry both its posted and its base figures
  regardless of the requested mode, so a client can explain any total it shows.
- Groups SHALL be ordered by their latest `accounting_date` descending, with
  groups having no accounting date ordered last, consistently across database
  backends.
- When the caller has no companies in scope, the endpoint SHALL return an empty
  page (not an error).

#### Scenario: One voucher's postings arrive as one group

- **WHEN** a client requests `GET /api/v1/erp-entries/vouchers` and a voucher has
  a net, a VAT, and a payable posting
- **THEN** one group is returned for that voucher with `entry_count` = 3, its
  three entries, and debit/credit totals covering all three

#### Scenario: Pagination does not split a voucher

- **WHEN** a client pages through vouchers with a `page_size` smaller than the
  number of matching entries
- **THEN** every returned group contains all of its entries, and `total` counts
  groups rather than entries

#### Scenario: A voucherless entry forms its own group

- **WHEN** entries exist with `voucher_id` null
- **THEN** each becomes a separate group with `voucher_id: null` and
  `entry_count` = 1, rather than being combined into one bucket

#### Scenario: Net spend excludes VAT and the payable

- **WHEN** a voucher posts 21658.04 to an expense account, 5414.51 to a VAT
  account, and 27072.55 credit to accounts payable
- **THEN** the group's `amount` is 21658.04, not 27072.55 and not 0

#### Scenario: A refund is negative spend

- **WHEN** a voucher credits an expense account
- **THEN** the group's `amount` is negative

#### Scenario: A voucher with no expense posting has no amount

- **WHEN** a payment voucher moves money between a payable and a bank account
- **THEN** the group's `amount` is `null` rather than `0`

#### Scenario: Mixed currencies are not summed

- **WHEN** a group's entries do not all share one currency and the request asks
  for original mode
- **THEN** the group's `currency` is `null`, signalling that its totals must not
  be presented as a single amount

#### Scenario: Base mode gives a mixed-currency voucher one total

- **WHEN** a voucher's postings were made in EUR and USD and all were converted
  for a DKK-based company
- **THEN** the group reports `currency: "DKK"` and one combined total instead of
  a null currency

#### Scenario: An unconverted posting is counted, not folded in

- **WHEN** one posting in a group has no base amount
- **THEN** the group's base totals exclude it and `unconverted_count` is 1

#### Scenario: Filters apply before grouping

- **WHEN** a client requests
  `GET /api/v1/erp-entries/vouchers?status=failed&from=2026-01-01`
- **THEN** only entries matching both filters are grouped, and groups whose
  entries all fell outside the filters do not appear

#### Scenario: Groups are tenant-scoped

- **WHEN** two organizations each have a voucher with the same `voucher_id`
- **THEN** a non-system-admin caller sees only its own organization's group, and
  the two are never merged

#### Scenario: No companies in scope yields an empty page

- **WHEN** a caller with no companies in scope lists voucher groups
- **THEN** the response is an empty page with `total` = 0 and HTTP 200
