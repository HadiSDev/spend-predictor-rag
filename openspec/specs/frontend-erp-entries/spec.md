# frontend-erp-entries Specification

## Purpose
TBD - created by archiving change erp-entries-page. Update Purpose after archive.
## Requirements
### Requirement: Entries page lists synced ERP data grouped by voucher

The app SHALL expose an authenticated `/entries` route that lists the organization's synced ERP entries from `GET /api/v1/erp-entries/vouchers`, grouped by voucher. Each group SHALL render as a single collapsed row showing its supplier, latest accounting date, entry type, posting count, and a single signed **Total** — the group's net spend — and SHALL be expandable to reveal its individual postings with their account code and name, description, debit, and credit.

- Amounts SHALL be presented per currency and SHALL NEVER be summed across
  currencies; a group whose entries disagree on currency SHALL show that the
  currencies are mixed instead of a combined figure.
- The group row SHALL NOT show separate debit and credit columns. A balanced
  voucher carries the same figure in both, so two columns would show one number
  twice; the signed Total is the figure a buyer reads. Debit and credit remain on
  the individual postings, where they are the ledger's actual content.
- A negative Total SHALL be visually distinguishable from a positive one, since
  it means spend was reduced rather than incurred.
- A group with no spend in it SHALL show no amount rather than a zero.
- Only **spend** postings SHALL be listed. VAT and the counterparty are ledger
  plumbing; the API retains them, the table does not show them, and omitting
  them is what makes the visible rows sum to the group's Total. When a connector
  declares no account types at all, every posting SHALL be shown rather than
  none.
- A posting SHALL show one signed amount rather than a debit and a credit. A
  credit on an expense account is a refund, so it renders negative.
- A posting's amount SHALL NOT render as a zero for an unused side. Connectors
  send `0.00` rather than null, so a truthiness check prints a zero on every row.
- A group SHALL be expandable only when it has more than one spend posting.
  Ordinary purchases have one, so most rows do not expand; a voucher split
  across several expense accounts is what expansion is for.
- A group that does not expand SHALL still open its posting's detail from the
  row itself, so the drawer does not become unreachable.
- A group of a single voucherless entry SHALL render as an ordinary row rather
  than an empty expandable group.
- Pagination SHALL be driven by the server's page envelope, so a voucher's
  postings are never split across pages.

#### Scenario: Vouchers are listed with their postings

- **WHEN** a signed-in user opens `/entries` and the organization has synced data
- **THEN** one row per voucher is shown with supplier, date, count, and totals,
  and expanding a row reveals its individual postings

#### Scenario: A voucherless entry is shown plainly

- **WHEN** an entry has no `voucher_id`
- **THEN** it appears as a single row without an expand affordance

#### Scenario: Only spend postings are listed, and they sum to the Total

- **WHEN** a voucher whose spend is split across two expense accounts is expanded
- **THEN** the two expense postings are shown with amounts summing to the
  group's Total, and the VAT and payable postings are not shown

#### Scenario: A single-spend voucher does not expand

- **WHEN** a voucher has one expense posting plus VAT and a payable
- **THEN** no expand control is offered, and activating the row opens that
  posting's detail

#### Scenario: An unused side never prints a zero

- **WHEN** a posting carries `0.00` on the side it does not use
- **THEN** no zero amount is rendered for it

#### Scenario: A refund reads as negative spend

- **WHEN** a voucher's net spend is negative
- **THEN** its Total renders as a negative amount, distinguishable from a
  positive one

#### Scenario: A voucher that spent nothing shows no amount

- **WHEN** a payment voucher has no expense posting
- **THEN** its Total is shown as empty rather than as 0.00

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

