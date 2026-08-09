# frontend-erp-entries Specification

## Purpose
TBD - created by archiving change erp-entries-page. Update Purpose after archive.
## Requirements
### Requirement: Entries page lists synced ERP data grouped by voucher

The app SHALL expose an authenticated `/entries` route that lists the organization's synced ERP entries from `GET /api/v1/erp-entries/vouchers`, grouped by voucher. Each group SHALL render as a single collapsed row showing its voucher, supplier, latest accounting date, and a single signed **Total Spend** — the group's net spend — and SHALL be expandable to reveal its postings, **one row per `ErpEntry`**, each with its account code and name, description, and its own signed amount.

- Every posting in the group SHALL be listed when it is expanded — expense, VAT,
  liability, asset, and income alike. The table SHALL NOT filter by account
  type. A balanced voucher's rows therefore sum to zero, which is what a general
  ledger shows, and there is no longer any case in which a posting the API
  returned is withheld from the screen.
- Consequently the group's figure SHALL be labelled **Total Spend** rather than
  Total. It is the net of the voucher's *expense* postings, so the rows beneath
  it do not add up to it, and a column named Total would assert that they do.
- A posting's amount SHALL be that entry's own `debit_amount − credit_amount`,
  shown as one signed figure rather than a debit and a credit. A credit on an
  expense account is a refund, so it renders negative.
- A posting's amount SHALL NOT render as a zero for an unused side. Connectors
  send `0.00` rather than null, so a truthiness check prints a zero on every row.
- Amounts SHALL be presented per currency and SHALL NEVER be summed across
  currencies; a group whose entries disagree on currency SHALL show that the
  currencies are mixed instead of a combined figure.
- The group row SHALL NOT show separate debit and credit columns. A balanced
  voucher carries the same figure in both, so two columns would show one number
  twice. Debit and credit remain on the individual postings, where they are the
  ledger's actual content.
- The table SHALL NOT carry an entry-type column. With payments excluded by the
  API, what remains is overwhelmingly `purchase_invoice`, and a column that
  reads the same on every row is noise. Entry type SHALL remain available as a
  filter and in the detail drawer.
- An expanded group SHALL render its own column headers above its postings —
  **Account**, **Description**, **Spend category**, **Amount** — because the table's header names
  the columns of a *voucher* row, not a posting's. Without them the account
  reads under Voucher, the line text under Date, and the posting's figure under
  Total Spend. The posting figure SHALL be headed **Amount**, not Total Spend: a
  VAT or payable posting is not spend.
- Each posting SHALL show the spend category of the invoice line it came from,
  as the **full path** (`Indirect › Legal › Professional Services`), with the
  leaf emphasised over the levels above it. The category is read from the
  posting's line and is never the posting's own, so several postings sharing a
  line SHALL all show the same category.
- A category level the categorizer did not fill SHALL be omitted from the path
  rather than rendered as an empty segment or a dangling separator.
- The cell SHALL be empty when the posting has no line (VAT, the payable) and
  when its line is not categorized yet, and the two SHALL look identical —
  neither is a state the reader can act on from this table.
- These headers SHALL be rendered once per open group, not once for the table,
  since groups expand independently and a header far above the rows it names
  does not name them.
- The voucher header row, a posting header row, and a posting row SHALL all span
  the same number of columns, counting `colSpan`. A row one column short
  silently shifts every posting's amount out from under the column that names it.
- A negative figure SHALL be visually distinguishable from a positive one, since
  it means spend was reduced rather than incurred.
- A group with no spend in it SHALL show no amount rather than a zero.
- A group SHALL be expandable whenever it has **more than one posting**. Since
  no posting is hidden, that is nearly every real voucher — which is the point:
  the ledger detail was always present and was previously unreachable.
- A group of a single entry SHALL still open that posting's detail from the row
  itself, so the drawer does not become unreachable where there is nothing to
  expand.
- A group of a single voucherless entry SHALL render as an ordinary row rather
  than an empty expandable group.
- Pagination SHALL be driven by the server's page envelope, so a voucher's
  postings are never split across pages.

#### Scenario: Vouchers are listed with their postings

- **WHEN** a signed-in user opens `/entries` and the organization has synced data
- **THEN** one row per voucher is shown with its voucher, supplier, date and
  Total Spend, and expanding a row reveals its individual postings

#### Scenario: No entry-type column is shown

- **WHEN** the table is rendered
- **THEN** it has no Type column, while entry type remains a filter

#### Scenario: Expanded postings carry their own column headers

- **WHEN** a voucher is expanded
- **THEN** Account, Description, Spend category and Amount headers are shown
  above its postings

#### Scenario: A categorized posting shows its full category path

- **WHEN** a posting's line is categorized Indirect / Legal / Professional
  Services
- **THEN** the cell reads that full path

#### Scenario: An uncategorized posting shows nothing

- **WHEN** a posting has no line, or its line is not categorized yet
- **THEN** the Spend category cell is empty, the same in both cases

#### Scenario: A missing level leaves no gap

- **WHEN** a line is categorized to only two levels
- **THEN** the path shows those two with no trailing separator

#### Scenario: Every row aligns to the same width

- **WHEN** a voucher is expanded
- **THEN** the voucher header row, the posting header row and each posting row
  span the same column count, so a posting's figure sits under Amount

#### Scenario: A voucherless entry is shown plainly

- **WHEN** an entry has no `voucher_id`
- **THEN** it appears as a single row without an expand affordance

#### Scenario: Every posting is listed, and they net to zero

- **WHEN** a voucher of an expense posting, an input-VAT posting, and a payable
  is expanded
- **THEN** all three are shown as separate rows, and their amounts sum to zero

#### Scenario: The group figure is not a sum of its rows

- **WHEN** a voucher is expanded
- **THEN** the group's column is labelled Total Spend and shows the voucher's net
  spend, which is not the sum of the visible rows

#### Scenario: A single-posting voucher does not expand

- **WHEN** a voucher has exactly one posting
- **THEN** no expand control is offered, and activating the row opens that
  posting's detail

#### Scenario: An unused side never prints a zero

- **WHEN** a posting carries `0.00` on the side it does not use
- **THEN** no zero amount is rendered for it

#### Scenario: A refund reads as negative spend

- **WHEN** a voucher's net spend is negative
- **THEN** its Total Spend renders as a negative amount, distinguishable from a
  positive one

#### Scenario: A voucher that spent nothing shows no amount

- **WHEN** a voucher has no expense posting — a transfer or an internal journal
  entry, payments having been excluded by the API
- **THEN** its Total Spend is shown as empty rather than as 0.00

#### Scenario: Mixed currencies are not combined

- **WHEN** a voucher's postings span more than one currency
- **THEN** the row indicates mixed currencies rather than displaying one summed
  amount

#### Scenario: Pages are fetched from the server

- **WHEN** the user moves to the next page
- **THEN** a new request is issued with the incremented `page`, and the table
  shows the returned groups

### Requirement: Entries are filtered by company, date range, entry type, status, and supplier

The Entries page SHALL provide filters for company, accounting-date range, entry type, status, and supplier, and SHALL pass them to the API as `company_id`, `from`/`to`, `entry_type`, `status`, and `vendor_id`.

- Company options SHALL come from `GET /api/v1/companies`, supplier options from
  the searchable `GET /api/v1/vendors`, and entry-type options from
  `GET /api/v1/reports/entries-summary`, so the offered values are ones the
  organization actually has rather than a hardcoded list.
- The entry-type options SHALL exclude any type the entry listings never return.
  The summary reports over *every* entry, including the payments the listings
  now exclude, so without this the filter would offer a value that can only ever
  produce an empty table.
- Filters SHALL compose, and the user SHALL be able to clear them back to the
  unfiltered view.
- Changing any filter SHALL reset pagination to the first page.

#### Scenario: A filter narrows the list

- **WHEN** the user selects a company and a date range
- **THEN** the request carries `company_id`, `from`, and `to`, and only matching
  vouchers are shown

#### Scenario: Filters compose

- **WHEN** the user selects a supplier and a status together
- **THEN** both `vendor_id` and `status` are sent and the result satisfies both

#### Scenario: Filtering resets the page

- **WHEN** the user is on page 3 and changes a filter
- **THEN** the request is issued with `page` = 1 rather than page 3

#### Scenario: Filters can be cleared

- **WHEN** the user clears the active filters
- **THEN** the unfiltered list is shown and the filter parameters are no longer
  sent

#### Scenario: An unlistable entry type is not offered

- **WHEN** the organization has payment entries, which the API excludes from
  every listing
- **THEN** `payment` is not offered as an entry-type filter option

### Requirement: Filter state is carried in the URL

The Entries page's filter and pagination state SHALL live in the route's search parameters, so a filtered view is linkable, survives a reload, and works with browser back and forward navigation. Unset filters SHALL be omitted from the URL rather than serialized as empty values.

#### Scenario: A filtered view is linkable

- **WHEN** the user applies filters and copies the URL into a new tab
- **THEN** the same filtered view loads, with the controls reflecting those
  filters

#### Scenario: Back navigation restores the previous filters

- **WHEN** the user changes a filter and then navigates back
- **THEN** the previous filter state is restored in both the URL and the controls

#### Scenario: The default view has a clean URL

- **WHEN** no filters are applied
- **THEN** the URL carries no empty filter parameters

### Requirement: An entry's full detail opens in a side drawer

Activating an individual posting SHALL open a side drawer showing its full detail from `GET /api/v1/erp-entries/{id}` — account code and name, voucher, source invoice, supplier, entry type, accounting date, currency, debit and credit, status, any error message, and the ERP's own entry identifier — while the table remains in place behind it. The drawer SHALL be dismissable by escape, by its close control, and by activating outside it.

#### Scenario: Detail opens for a posting

- **WHEN** the user activates one posting inside an expanded voucher
- **THEN** a drawer opens with that entry's full detail and the table stays
  rendered behind it

#### Scenario: A failed entry shows why

- **WHEN** the opened entry has a failed status
- **THEN** the drawer shows the status and its error message

#### Scenario: The drawer is dismissable

- **WHEN** the user presses escape or activates the close control
- **THEN** the drawer closes and focus returns to the row that opened it

### Requirement: Entries page has explicit loading, empty, and error states

The Entries page SHALL show loading placeholders while its query is in flight, an explicit empty state when no entries match, and an error state when the request fails — never a bare or ambiguous table.

- The empty state SHALL distinguish "no synced data yet" from "no entries match
  these filters", and in the latter case SHALL offer to clear the filters.
- When a supplier filter is active, the empty state SHALL note that postings not
  linked to an invoice carry no supplier and are therefore excluded.

#### Scenario: Loading state

- **WHEN** the voucher query is in flight
- **THEN** skeleton placeholders are shown rather than an empty table

#### Scenario: Nothing synced yet

- **WHEN** the organization has no entries at all
- **THEN** an empty state explains that no ERP data has been synced yet

#### Scenario: No matches for the current filters

- **WHEN** filters are active and nothing matches
- **THEN** the empty state says so and offers to clear the filters

#### Scenario: Request failure

- **WHEN** the request to the web API fails
- **THEN** an error state is shown explaining the failure, not an empty result

### Requirement: Amounts are presented in the company's base currency

Amounts SHALL be presented in the company's base currency across the entries
page, its voucher groups, its postings, and the dashboard's report figures, with
the base currency mode requested from the API.

- A voucher group whose postings were made in several currencies SHALL show one
  combined total in the base currency rather than reporting mixed currencies,
  provided its postings are converted.
- Money SHALL still never be summed across currencies: when a group's postings do
  not all share one base currency, the existing mixed-currency treatment SHALL
  apply unchanged.
- When the selected scope spans companies with different base currencies, figures
  SHALL NOT be combined across them. Totals SHALL be grouped by the currency the
  API reports on each row, which is what keeps two base currencies apart without
  the client reasoning about companies.

#### Scenario: A mixed-currency voucher shows one total

- **WHEN** a voucher's postings were made in EUR and USD for a DKK-based company
  and all are converted
- **THEN** the group shows a single DKK total instead of a mixed-currency
  indicator

#### Scenario: Base currencies are not combined across companies

- **WHEN** the current scope covers a DKK company and a EUR company
- **THEN** their figures are not added into one number

### Requirement: The original amount and the rate used are one hover away

Any amount shown converted SHALL be able to explain itself: hovering or focusing
a converted amount SHALL reveal the as-posted amount and currency, the rate
applied, and the date that rate was published for. The entry's detail view SHALL
show the same information as labelled fields rather than only as a tooltip.

- The disclosure SHALL be keyboard-reachable, not hover-only.
- An amount posted in the base currency needs no disclosure and SHALL NOT show a
  rate of 1 as if it were a conversion.

#### Scenario: A converted amount explains itself

- **WHEN** the user hovers a converted total
- **THEN** the original amount and currency, the rate, and the rate date are
  shown

#### Scenario: The detail view shows the conversion in full

- **WHEN** the user opens an entry's detail view
- **THEN** the posted amount and currency, the base amount, the rate, and the
  rate date are all shown as labelled fields

#### Scenario: Keyboard users get the same information

- **WHEN** the user focuses a converted amount with the keyboard
- **THEN** the same disclosure appears

#### Scenario: A same-currency amount shows no conversion

- **WHEN** an entry was posted in the company's own currency
- **THEN** no rate or original-amount disclosure is offered for it

### Requirement: Amounts that could not be converted are visibly marked

A row or group carrying money that has no base-currency figure SHALL show that
money in its posted currency, visibly marked as not converted, and SHALL NOT
render it as an empty cell, a zero, or a base-currency figure.

Where the API reports how many of a group's contributing postings were
unconverted, the group SHALL surface that the shown total is incomplete rather
than presenting it as the full figure.

#### Scenario: An unconverted posting is marked, not hidden

- **WHEN** a posting has no base amount
- **THEN** its posted amount and currency are shown with an indication that it
  is not converted

#### Scenario: An incomplete total says so

- **WHEN** a group's total excludes unconverted postings
- **THEN** the group indicates that some of its postings are not included in the
  figure

#### Scenario: Unconverted money is never shown as zero

- **WHEN** every contributing row is unconverted
- **THEN** the total is not rendered as `0.00` in the base currency



