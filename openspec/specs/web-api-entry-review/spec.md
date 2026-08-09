# web-api-entry-review Specification

## Purpose

Read endpoints for `ErpEntry` data (raw GL postings) on the web API: a tenant-scoped list with filters and pagination, and a tenant-scoped single-entry fetch. Ground-truth (`gt_*`) columns are never exposed, and out-of-scope entries return 404 so existence is not leaked across tenants.
## Requirements
### Requirement: List ERP entries with filters and pagination

The API SHALL expose `GET /api/v1/erp-entries` returning a paginated list of `ErpEntry` rows scoped to the caller's tenant, so clients can read raw GL postings.

- Results SHALL be restricted to companies within the caller's scope; a
  non-system-admin SHALL only see entries for their organization's companies, and
  a system admin MAY read across organizations.
- The endpoint SHALL support pagination (`page`, `page_size`) and return a
  `Page`-shaped body (`items`, `page`, `page_size`, `total`).
- The endpoint SHALL support optional filters: `company_id`, `entry_type`,
  `voucher_id`, `source_invoice_id`, `status`, `from`, `to`, and `vendor_id`.
  Filters compose (AND).
- `from` and `to` SHALL filter on `accounting_date` inclusively, matching the
  parameter names the reporting endpoints already use. An entry with no
  `accounting_date` SHALL NOT match a bounded range.
- `vendor_id` SHALL match entries whose `source_invoice_id` refers to an invoice
  with that vendor. Entries with no source invoice SHALL NOT match any
  `vendor_id`, because an unlinked posting has no known supplier.
- Entries whose `entry_type` is `payment` SHALL NOT be returned. A payment
  settles an invoice that is already accounted for — the money moves, nothing is
  spent — so it is noise in a spend product, and its postings land on the
  payable and bank accounts a customer has no reason to enable for sync. This is
  a product rule, not a default: supplying `entry_type=payment` SHALL return an
  empty page rather than overriding the exclusion, and `total` SHALL count only
  what is returned. The exclusion SHALL be narrow — `credit_note` and
  `journal_entry` both move real spend and SHALL be returned.
- Entries posted to an account with `sync_enabled = false` SHALL NOT be
  returned. The toggle is the customer's statement of which accounts are part of
  their spend picture; accounts are enabled when first discovered and disabling
  one deletes nothing, so without this the listings keep showing rows from
  accounts the settings say are excluded. Filtering rather than deleting keeps it
  reversible: re-enabling an account restores its entries with no re-sync.
- Both exclusions SHALL be expressed once, in the condition set shared by the flat
  list and the voucher groups, so the two can never disagree about what exists.
- Entries SHALL be ordered by `accounting_date` descending with **undated
  entries last**, then by `voucher_id`, then by `id`. Ordering by voucher within
  a date keeps one voucher's postings adjacent, so a flat ledger view reads as a
  ledger rather than as scattered rows; the trailing `id` makes the order total,
  so pagination cannot repeat or skip a row. Undated entries sort last for the
  same reason the grouped endpoint does it — a missing date is not a recent one,
  and the two endpoints must not disagree.
- When the caller has no companies in scope, the endpoint SHALL return an empty
  page (not an error).
- The response SHALL NOT include ground-truth (`gt_*`) columns.

#### Scenario: Paginated, tenant-scoped list

- **WHEN** an authenticated member requests `GET /api/v1/erp-entries`
- **THEN** the response contains only entries whose `company_id` is in the
  caller's scope, paginated with a `total` count

#### Scenario: Filter by source invoice

- **WHEN** a client requests `GET /api/v1/erp-entries?source_invoice_id=<id>`
- **THEN** only entries linked to that invoice (and within scope) are returned

#### Scenario: Filter by voucher and entry type

- **WHEN** a client requests `GET /api/v1/erp-entries?voucher_id=V1&entry_type=purchase_invoice`
- **THEN** only entries matching both filters (and within scope) are returned

#### Scenario: Filter by accounting date range

- **WHEN** a client requests `GET /api/v1/erp-entries?from=2026-01-01&to=2026-01-31`
- **THEN** only entries whose `accounting_date` falls within that inclusive range
  are returned, and entries with no `accounting_date` are excluded

#### Scenario: Filter by supplier

- **WHEN** a client requests `GET /api/v1/erp-entries?vendor_id=<id>`
- **THEN** only entries whose source invoice belongs to that vendor are returned,
  and entries with no `source_invoice_id` are excluded

#### Scenario: Payments are not listed

- **WHEN** a tenant has payment vouchers alongside purchase invoices and a client
  lists entries, or voucher groups
- **THEN** no entry of type `payment` appears in either response, and the
  purchase invoices, credit notes and journal entries are all still returned

#### Scenario: A deselected account's entries are not listed

- **WHEN** an account is set `sync_enabled = false` and it has entries already
  persisted
- **THEN** neither listing returns them, and `total` counts only what is returned

#### Scenario: Re-enabling an account restores its entries

- **WHEN** that account is set back to `sync_enabled = true`
- **THEN** its entries appear in the listings again, without a re-sync

#### Scenario: A voucher of only deselected postings produces no group

- **WHEN** every posting of a voucher sits on deselected accounts
- **THEN** no group is returned for it

#### Scenario: Asking for payments returns nothing

- **WHEN** a client requests `GET /api/v1/erp-entries?entry_type=payment`
- **THEN** an empty page with `total` = 0 is returned, rather than the payments

#### Scenario: A single entry is still fetchable by id

- **WHEN** a client requests `GET /api/v1/erp-entries/{id}` for a payment entry
  in its own tenant
- **THEN** the entry is returned; the exclusion governs what is listed, and no
  listing offers that id in the first place

#### Scenario: Postings of one voucher stay adjacent

- **WHEN** two vouchers posted on the same accounting date each have several
  postings and a client lists them
- **THEN** the postings of each voucher appear consecutively rather than
  interleaved

#### Scenario: Undated entries sort last

- **WHEN** the tenant has entries with and without an `accounting_date`
- **THEN** the dated entries are returned first, newest first, and the undated
  ones follow

#### Scenario: No companies in scope yields an empty page

- **WHEN** a caller with no companies in scope lists entries
- **THEN** the response is an empty page with `total` = 0 and HTTP 200

### Requirement: Fetch a single ERP entry

The API SHALL expose `GET /api/v1/erp-entries/{entry_id}` returning one `ErpEntry`, and SHALL return 404 when the entry does not exist or is outside the caller's tenant scope.

- A found entry within scope SHALL be returned as an `ErpEntryRead`, carrying the
  same denormalized account and vendor fields as the list representation, so an
  entry reads identically wherever it is fetched.
- An entry that exists but belongs to a company outside the caller's scope SHALL
  return 404 (not 403), so existence is not leaked across tenants.

#### Scenario: Fetch an in-scope entry

- **WHEN** a client requests `GET /api/v1/erp-entries/{id}` for an entry in its scope
- **THEN** the single entry is returned, including its account code and name

#### Scenario: Out-of-scope or unknown entry returns 404

- **WHEN** a client requests an entry id that is unknown or belongs to another tenant
- **THEN** the API responds 404 Not Found

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

### Requirement: Entry representation carries its source line and that line's category

`ErpEntryRead` SHALL expose the invoice line a posting came from and the spend
category of that line, resolved server-side.

- The payload SHALL carry `source_invoice_line_id`, and
  `spend_category_level_1`, `spend_category_level_2`, `spend_category_level_3`
  read from the linked `InvoiceLine`.
- The category SHALL be read from the **line**, never from the entry. A posting
  is never categorized; one line may have many postings, and they SHALL all
  report that line's category.
- All four SHALL be null when the posting has no source line, and the three
  category levels SHALL also be null when the line exists but is not yet
  categorized. The two cases SHALL be indistinguishable in the payload, because
  neither is actionable from an entry listing.
- The resolution SHALL happen in the one shared select that builds every
  `ErpEntryRead`, so the flat list, the voucher groups and the detail endpoint
  cannot disagree, and a client never fetches the line per row.

#### Scenario: A posting reports its line's category

- **WHEN** a posting is linked to a categorized invoice line
- **THEN** its payload carries that line's id and its three category levels

#### Scenario: Several postings report the same category

- **WHEN** two postings share one invoice line
- **THEN** both report that line's id and the same category levels

#### Scenario: An uncategorized line yields no category

- **WHEN** a posting's line exists but has not been categorized
- **THEN** the line id is present and all three category levels are null

#### Scenario: A posting with no line yields no category

- **WHEN** a posting has no source invoice line
- **THEN** the line id and all three category levels are null

### Requirement: List ERP entries grouped by voucher

The API SHALL expose `GET /api/v1/erp-entries/vouchers` returning a paginated list of voucher groups, each carrying its constituent entries, so a client can present the several postings that make up one spend event as a single unit.

- The endpoint SHALL be tenant-scoped and SHALL accept the same filters as
  `GET /api/v1/erp-entries` (`company_id`, `entry_type`, `status`, `from`, `to`,
  `vendor_id`, `source_invoice_id`), applied to the entries before grouping.
- Entries of type `payment`, and entries on accounts with `sync_enabled = false`,
  SHALL both be excluded **before grouping**, by the same shared condition set as
  `GET /api/v1/erp-entries`. A voucher left with no postings therefore produces
  no group at all, and a group's `entry_count` and totals SHALL cover only the
  entries it actually returns — a group must never total a row it does not show.
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
- When no entry in the group is posted to an expense account — a transfer or an
  internal journal entry, which moves money without spending it — `amount` SHALL
  be `null` rather than `0`, so "no spend here" is not shown as a zero figure.
  (Payment vouchers, the other case this once covered, no longer reach the
  response at all.)
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

- **WHEN** a journal-entry voucher moves money between a payable and a bank
  account
- **THEN** the group's `amount` is `null` rather than `0`

#### Scenario: A payment voucher produces no group

- **WHEN** a tenant has a voucher whose postings are all of type `payment`
- **THEN** no group is returned for it, and the vouchers that move real spend
  are unaffected

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

### Requirement: A voucher carries its invoice lines

`GET /api/v1/erp-entries/vouchers` and the voucher-detail endpoints SHALL carry
the voucher's **invoice lines** alongside its entries, resolved server-side from
the voucher's source invoice.

- Each line SHALL carry its description, quantity, unit price, amount, its
  base-currency conversion, its categorization result and status, and its
  `origin`. The client must be able to render the expanded voucher without a
  second request per row.
- The voucher SHALL also carry its invoice's `doc_status` and `doc_error`, so
  the reader can tell provisional lines from read-the-document lines and see why
  processing failed.
- A voucher with no source invoice — a journal entry, a transfer — SHALL carry
  an empty line list, not an error. Lines are not universal and their absence is
  ordinary.
- The lines SHALL be ordered deterministically, so a voucher reads the same on
  every request.
- Adding lines SHALL NOT change which vouchers are returned, how they are
  grouped, how they are paginated, or what their amount is. The grouping,
  filtering and `currency_mode` rules are unchanged, and the voucher's amount
  remains the net of its **expense postings** — never a sum of its lines, which
  may legitimately differ.

#### Scenario: A voucher arrives with its lines

- **WHEN** a caller lists voucher groups and a voucher's invoice has three lines
- **THEN** the group carries those three lines with their descriptions, amounts,
  conversions, categories, statuses and origins

#### Scenario: Processing state travels with the voucher

- **WHEN** a voucher's invoice is `failed`
- **THEN** the group carries `doc_status = failed` and the failure's reason

#### Scenario: A voucher with no invoice has no lines

- **WHEN** a journal-entry voucher with no source invoice is returned
- **THEN** its line list is empty and the response is `200 OK`

#### Scenario: Lines do not change the voucher's amount

- **WHEN** a voucher's extracted lines sum to a figure other than its net
  expense postings
- **THEN** the voucher's amount is still the net of its expense postings

#### Scenario: Grouping and pagination are unaffected

- **WHEN** the same request is made before and after lines are carried
- **THEN** the same vouchers are returned, in the same order, on the same pages

### Requirement: An entry's category is null once its line is no longer identifiable

`ErpEntryRead.spend_category_level_1/2/3` SHALL remain read through
`source_invoice_line_id`, and SHALL be null when document extraction has
replaced the invoice's lines and left the posting unlinked.

- The category SHALL NOT be recovered by matching a posting to an extracted line
  on amount, account or description. An extracted line has no ERP line identity,
  and a guessed link would attach a category to a posting on no evidence — the
  same reason the sync derives the link rather than matching it.
- This SHALL NOT reduce what the reader sees, because the category is now shown
  on the line, which is what the Entries page lists.

#### Scenario: A posting unlinked by extraction shows no category

- **WHEN** an invoice's ERP lines have been replaced by extracted ones and its
  postings are unlinked
- **THEN** each posting's category levels are null

#### Scenario: No category is guessed

- **WHEN** exactly one extracted line carries the same amount as an unlinked
  posting
- **THEN** the posting's category is still null



