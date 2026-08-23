# frontend-erp-entries Specification

## Purpose
TBD - created by archiving change erp-entries-page. Update Purpose after archive.
## Requirements
### Requirement: Entries page lists synced ERP data grouped by voucher

The app SHALL expose an authenticated `/entries` route that lists the organization's synced ERP data from `GET /api/v1/erp-entries/vouchers`, grouped by voucher. Each group SHALL render as a single collapsed row showing its voucher, supplier, latest accounting date, and a single signed **Total Spend** — the group's net spend — and SHALL be expandable to reveal **the voucher's invoice lines, one row per `InvoiceLine`**, each with its description, quantity, amount and spend category.

- The expanded rows SHALL be the voucher's **invoice lines**, not its postings.
  A posting is what the bookkeeper wrote; a line is what was bought, and the
  line is what carries a description, a category and a human's verification.
  The postings remain available in full on the voucher panel's Postings tab,
  where they are read as ledger evidence rather than as spend.
- The group's figure SHALL remain **Total Spend** — the net of the voucher's
  *expense postings*, taken from the server — and SHALL NOT be a sum of the
  lines beneath it. Extracted lines may legitimately differ from the ledger by
  rounding, and a column named Total would assert an equality that does not hold.
- A line's amount SHALL be its own signed figure. A credit line is a discount or
  a refund and renders negative.
- A line SHALL NOT render a zero for an amount it does not carry.
- Amounts SHALL be presented per currency and SHALL NEVER be summed across
  currencies; a group whose data disagrees on currency SHALL show that the
  currencies are mixed instead of a combined figure.
- The group row SHALL NOT show separate debit and credit columns. Debit and
  credit are a property of a posting, not of a line, and they remain on the
  Postings tab where they are the ledger's actual content.
- The table SHALL NOT carry an entry-type column. Entry type SHALL remain
  available as a filter and on the voucher panel.
- An expanded group SHALL render its own column headers above its lines —
  **Description**, **Quantity**, **Unit**, **Unit price**, **Spend category**,
  **Amount** —
  because the table's header names the columns of a *voucher* row, not a line's.
  The line figure SHALL be headed **Amount**, not Total Spend.
- **Unit** SHALL be its own column beside Quantity, not appended to the quantity
  cell: the quantity is a right-aligned tabular figure meant to be scanned down,
  and a unit inside that cell breaks the alignment on every row that has one. An
  empty Unit cell SHALL read as empty rather than as a substituted default.
- **Unit price** SHALL be shown as its source stated it, in that source's own
  currency, and SHALL NOT be converted. Only the line's *amount* carries a
  stored base figure; deriving a base unit price at render time would make the
  table the one place in the app that converts money client-side.
- A line row carries one more column than a voucher row, so a voucher row's
  cells SHALL span the difference. The **Amount** column and the **Total Spend**
  column SHALL remain the same column: a line figure one column right of the
  total it belongs to is read against the wrong header.
- The voucher row SHALL carry an **Invoice no.** column, showing the number read
  from the document in preference to the as-posted one. Where the two exist and
  disagree, both SHALL be reachable — a disagreement means the ERP's number is
  wrong or the scan belongs to another invoice, and either is worth seeing.
  Where neither exists, the cell SHALL be empty.
- Each line SHALL show its spend category as the **full path**
  (`Indirect › Legal › Professional Services`), with the leaf emphasised over the
  levels above it.
- A category level the categorizer did not fill SHALL be omitted from the path
  rather than rendered as an empty segment or a dangling separator.
- The cell SHALL be empty when the line is not categorized yet.
- These headers SHALL be rendered once per open group, not once for the table,
  since groups expand independently and a header far above the rows it names
  does not name them.
- The voucher header row, a line header row, and a line row SHALL all span the
  same number of columns, counting `colSpan`. A row one column short silently
  shifts every amount out from under the column that names it.
- A negative figure SHALL be visually distinguishable from a positive one, since
  it means spend was reduced rather than incurred.
- A group with no spend in it SHALL show no amount rather than a zero.
- A group SHALL be expandable whenever its voucher has **at least one line**.
- A group with no lines — a journal entry, a transfer, a voucher whose postings
  are all non-expense — SHALL render as an ordinary row that still opens the
  voucher panel, so its postings stay reachable where there is nothing to expand.
- A group of a single voucherless entry SHALL render as an ordinary row rather
  than an empty expandable group.
- Pagination SHALL be driven by the server's page envelope, so a voucher's lines
  are never split across pages.

#### Scenario: Vouchers are listed with their lines

- **WHEN** a signed-in user opens `/entries` and the organization has synced data
- **THEN** one row per voucher is shown with its voucher, supplier, date and
  Total Spend, and expanding a row reveals that voucher's invoice lines

#### Scenario: Postings are not the expanded rows

- **WHEN** a voucher of one expense posting, one input-VAT posting and one
  payable is expanded, and its invoice carries two lines
- **THEN** two rows are shown — the two lines — and neither the VAT posting nor
  the payable appears among them

#### Scenario: No entry-type column is shown

- **WHEN** the table is rendered
- **THEN** it has no Type column, while entry type remains a filter

#### Scenario: Expanded lines carry their own column headers

- **WHEN** a voucher is expanded
- **THEN** Description, Quantity, Unit, Unit price, Spend category and Amount
  headers are shown above its lines

#### Scenario: A line states its unit price as stated

- **WHEN** a line was stated at 1.600,00 per unit
- **THEN** the Unit price cell reads that figure, unconverted

#### Scenario: A line with no unit price shows none

- **WHEN** the source stated an amount and no unit price — the ordinary case
  for an ERP bill line
- **THEN** the Unit price cell is empty

#### Scenario: A line states the unit its quantity is counted in

- **WHEN** a line reads 12 with a unit of `hours`
- **THEN** the Quantity cell reads 12 and the Unit cell reads `hours`

#### Scenario: A line with no unit shows none

- **WHEN** a line has no unit
- **THEN** its Unit cell is empty, with no default substituted

#### Scenario: The number printed on the document is preferred

- **WHEN** a voucher's invoice was posted with the bill id as its number and the
  document reads "2026-0412"
- **THEN** the Invoice no. column reads "2026-0412"

#### Scenario: A disagreement between the two numbers is reachable

- **WHEN** the posted number and the document's number differ
- **THEN** both are available to the reader rather than one silently winning

#### Scenario: An invoice with no number anywhere shows none

- **WHEN** neither number exists
- **THEN** the Invoice no. cell is empty

#### Scenario: A categorized line shows its full category path

- **WHEN** a line is categorized Indirect / Legal / Professional Services
- **THEN** the cell reads that full path

#### Scenario: An uncategorized line shows nothing

- **WHEN** a line is not categorized yet
- **THEN** its Spend category cell is empty

#### Scenario: A missing level leaves no gap

- **WHEN** a line is categorized to only two levels
- **THEN** the path shows those two with no trailing separator

#### Scenario: Every row aligns to the same width

- **WHEN** a voucher is expanded
- **THEN** the voucher header row, the voucher row, the line header row and each
  line row span the same column count, so a line's figure sits under Amount and
  Amount sits under Total Spend

#### Scenario: A voucherless entry is shown plainly

- **WHEN** an entry has no `voucher_id`
- **THEN** it appears as a single row without an expand affordance

#### Scenario: The group figure is not a sum of its rows

- **WHEN** a voucher whose extracted lines sum to 4.810,00 has a net expense of
  4.812,00
- **THEN** the group's column is labelled Total Spend and shows 4.812,00

#### Scenario: A voucher with no lines still opens

- **WHEN** a journal-entry voucher carrying no invoice lines is rendered
- **THEN** it has no expand control, and activating the row opens the voucher
  panel where its postings are listed

#### Scenario: An unused side never prints a zero

- **WHEN** a line carries no amount
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

- **WHEN** a voucher's data spans more than one currency
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

Activating a voucher row, or a line within it, SHALL open the URL-addressable voucher panel beside the table, which SHALL carry a **Lines** tab and a **Postings** tab in addition to its existing tabs, with the table remaining in place behind it. The panel SHALL be dismissable by escape, by its close control, and by activating outside it.

- The **Lines** tab SHALL present the voucher's invoice lines **one at a time**
  as a paged card, with Previous / Next navigation and a position indicator, and
  SHALL be where a line's category is corrected. It is the tab that opens when a
  line is activated from the expanded table, and it SHALL open on the line that
  was activated rather than on the first. The paging behaviour is specified in
  `frontend-line-paging`.
- The **Postings** tab SHALL list every `ErpEntry` of the voucher — expense,
  VAT, liability, asset and income alike — each with its account code and name,
  entry type, accounting date, description, debit, credit, status, any error
  message, and the ERP's own entry identifier. It SHALL NOT filter by account
  type: a balanced voucher's postings sum to zero, which is what a general
  ledger shows.
- Postings SHALL be presented as flat evidence text, never as disabled inputs.
  They are ERP-posted values and nothing about them is correctable here.
- The tab SHALL be carried in the URL like the panel's other tabs, so a link to
  a voucher's postings opens on the postings.
- A failed posting SHALL show its status and error message.

#### Scenario: Detail opens for a line

- **WHEN** the user activates one line inside an expanded voucher
- **THEN** the voucher panel opens on its Lines tab showing that line as the
  paged card, and the table stays rendered behind it

#### Scenario: Postings are one tab away

- **WHEN** the user opens the Postings tab of a voucher of an expense posting,
  an input-VAT posting and a payable
- **THEN** all three are listed with their accounts and amounts, and they sum to
  zero

#### Scenario: A failed entry shows why

- **WHEN** a posting has a failed status
- **THEN** the Postings tab shows the status and its error message

#### Scenario: Postings are not editable

- **WHEN** the Postings tab is rendered
- **THEN** its values are text, with no disabled inputs

#### Scenario: The open tab is linkable

- **WHEN** a link carrying the postings tab is opened
- **THEN** the panel opens on the Postings tab

#### Scenario: The drawer is dismissable

- **WHEN** the user presses escape or activates the close control
- **THEN** the panel closes and focus returns to the row that opened it

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

### Requirement: Provisional lines are visibly provisional

A line whose `origin` is `entry_fallback` SHALL be marked, in the expanded table
and on the Lines tab, as standing in for a posting rather than read from a
document.

- The mark SHALL explain itself on hover and to a keyboard or screen-reader
  user, not by colour or an unlabelled icon alone.
- A line whose `origin` is `document_ai` SHALL carry no mark. The extracted case
  is the ordinary one and marking it would make the marking meaningless.
- The distinction SHALL come from the payload's `origin`, never from inferring
  it — a stand-in line and an extracted line can read identically.
- The mark SHALL NOT be an error state. A voucher with no scan is normal, and
  presenting it as a problem would flag most of the ledger.

#### Scenario: A stand-in line says what it is

- **WHEN** a line with `origin = entry_fallback` is rendered
- **THEN** it carries a mark explaining that it stands in for a posting because
  no document was read

#### Scenario: An extracted line is unmarked

- **WHEN** a line with `origin = document_ai` is rendered
- **THEN** it carries no provenance mark

#### Scenario: The mark is not an error

- **WHEN** a voucher's lines are all stand-ins because it has no attached scan
- **THEN** nothing on the row is presented as a failure

#### Scenario: The explanation reaches assistive technology

- **WHEN** a keyboard user focuses the mark
- **THEN** the same explanation is announced as a pointer user sees

### Requirement: Document processing state is shown and can be retriggered

The voucher panel SHALL show the invoice's `doc_status`, and SHALL offer a
retrigger action that posts to `POST /api/v1/invoices/{id}/reprocess`.

- A `failed` invoice SHALL show its `doc_error` — the reason, in the words the
  API returned — beside the action, so the user is not asked to retry blind.
- The action SHALL be offered only when the invoice has a document and is not
  currently `processing`, matching what the API will accept. Offering an action
  that will 409 teaches the user to distrust the screen.
- The action SHALL be offered only to a user with a management role, since that
  is what the endpoint requires.
- A `pending` or `processing` invoice SHALL say so, so a user who has just
  retriggered can see that the work is queued rather than lost.
- After a successful retrigger the panel SHALL reflect the new state without a
  manual reload, and the voucher's lines SHALL be refetched when processing
  later replaces them.
- An invoice with no document SHALL show that plainly and offer no action, not a
  disabled control.

#### Scenario: A failure explains itself

- **WHEN** an invoice's `doc_status` is `failed`
- **THEN** the panel shows the failure and its reason, with a retrigger action

#### Scenario: Retriggering is reflected immediately

- **WHEN** a manager retriggers processing
- **THEN** the panel shows the invoice as `pending` without a reload

#### Scenario: No action where the API would refuse

- **WHEN** the invoice is `processing`, or has no attached document
- **THEN** no retrigger action is offered

#### Scenario: A read-only member is not offered the action

- **WHEN** a `viewer` opens a failed invoice's voucher
- **THEN** the failure and its reason are shown and no retrigger action is
  offered

#### Scenario: A voucher with no scan states it plainly

- **WHEN** the invoice's `doc_status` is `not_applicable`
- **THEN** the panel says no document is attached, with no action and no error

### Requirement: Lines can be filtered by provenance

The Entries page's filters SHALL include line provenance, passed to the API as
`origin`, so a user can find the spend that is still standing on its postings.

- The option SHALL sit with the existing filters and follow the same rules: it
  is carried in the URL, it composes with the others, it resets the page, and it
  is cleared by Clear filters.

#### Scenario: Provenance narrows the list

- **WHEN** the user filters to stand-in lines
- **THEN** only vouchers whose lines are stand-ins are listed, and the URL
  carries the filter

#### Scenario: It composes and clears like the rest

- **WHEN** the provenance filter is combined with a supplier and then cleared
- **THEN** both apply together, and Clear filters removes both

### Requirement: A line's category is chosen from the tree, not typed

In the voucher slide-over, correcting a line's categorization SHALL be a **tree selector** over the company's assigned spend tree, replacing the free-text level inputs. The reviewer SHALL pick a node; the levels SHALL be derived from that node's path and shown as read-back text, never as separately editable strings.

Free text cannot be right here: a typed level that matches no node produces a categorization resolving to nothing, which is exactly the silent failure the stored `spend_category_id` exists to prevent.

The selector SHALL:

- present the tree level by level, so the reviewer sees where in the taxonomy they are,
- offer a search across all node paths, so a known leaf is reachable without drilling,
- show the full path of the chosen node before saving,
- support trees of three and four levels without a layout change,
- allow choosing a non-leaf node when the tree's own shape permits it, since a three-level tree's level-2 node is a legitimate answer.

#### Scenario: Picking a node sets the whole path

- **WHEN** a reviewer selects `Indirect > Technology > Cloud Infrastructure`
- **THEN** all three levels are shown as the chosen path and the save sends that node's id

#### Scenario: Search reaches a deep leaf

- **WHEN** a reviewer types part of a level-4 node's name
- **THEN** matching nodes are listed with their full paths and selecting one sets the path

#### Scenario: Four levels need no different screen

- **WHEN** the company's tree has four levels
- **THEN** the selector presents the fourth level in the same control, with no separate input appearing

#### Scenario: Levels are not free text

- **WHEN** the category editor is open
- **THEN** there is no editable text input for `level_1`, `level_2`, `level_3`, or `level_4`

### Requirement: A category that no longer resolves is shown as needing review

A line whose stored categorization no longer resolves to a node in its company's assigned tree SHALL be marked in the entries view and in the slide-over as needing review, showing the stored path as the previous decision rather than as the current category.

The stored levels SHALL remain visible — they are the record of what was decided, and hiding them would destroy the reviewer's only clue about what the line was. The marking SHALL be distinguishable from `ai_failed`: nothing failed, the taxonomy moved.

#### Scenario: A stale line is marked

- **WHEN** a line's category does not resolve in the company's assigned tree
- **THEN** the line is marked as needing review and its stored path is presented as the previous category

#### Scenario: Re-picking clears the mark

- **WHEN** a reviewer selects a node from the current tree and saves
- **THEN** the line is no longer marked and shows the new path as its category

#### Scenario: Stale is not failure

- **WHEN** stale lines and `ai_failed` lines are both present
- **THEN** they are visually and textually distinct

### Requirement: The category editor degrades honestly when there is no tree

When a line's company has no assigned spend tree, the category editor SHALL say so and SHALL NOT offer a selector over an empty set or fall back to free-text inputs. It SHALL point a manager at where the tree is chosen.

#### Scenario: No tree, no selector

- **WHEN** the line's company has no assigned spend tree
- **THEN** the editor states that no spend tree is assigned and links to company settings instead of showing an empty picker

#### Scenario: The rest of the line still reads

- **WHEN** no tree is assigned
- **THEN** the line's description, amount, status, and rationale remain visible as evidence

### Requirement: A line is labelled by its item name

A line's label SHALL be its `item_name`, falling back to `description` when the
name is null, and to an explicit placeholder when both are — wherever a line is
labelled: the expanded table row, the paged line card, and the audit feed.

The description SHALL remain visible on the line card as its own field, so a
supplier's prose is not lost behind the name.

#### Scenario: The name is the label

- **WHEN** a line has both an item name and a description
- **THEN** the row and the card are labelled with the item name, and the
  description is shown as its own field on the card

#### Scenario: The description stands in for a missing name

- **WHEN** a line has a null `item_name` and a description
- **THEN** the description is used as the label

#### Scenario: A line with neither is marked, not blank

- **WHEN** a line has neither
- **THEN** a placeholder is shown rather than an empty cell

### Requirement: Money, quantities and dates use their proper controls

Every editable numeric and date field in the voucher panel SHALL use the
library's typed controls rather than a text input.

- Monetary fields — a line's `unit_price` and `amount`, an invoice's `total` and
  `tax` — SHALL use `CurrencyInput`, bound to the invoice's currency, at 2
  decimal places.
- `quantity` SHALL use `NumberInput` at up to 4 decimal places, with trailing
  zeros trimmed on display. It is stored as `Numeric(12,4)`, and clamping the
  control to 2 would round a stored value on save.
- `unit_price` SHALL likewise accept up to 4 decimal places for the same reason,
  while displaying 2 by default.
- `invoice_date` SHALL use `DatePicker`, and SHALL submit an ISO `YYYY-MM-DD`
  string, which is what the API takes.
- A value that cannot be parsed SHALL NEVER be submitted as `null`. An empty
  field means null; unparseable input SHALL be rejected in the field, with the
  save blocked until it is fixed.

#### Scenario: A stored figure is shown at its display scale

- **WHEN** a line whose amount is stored as `1234.50000` is opened
- **THEN** the amount field shows `1,234.50`

#### Scenario: A European decimal is not destroyed

- **WHEN** the reviewer types `1,5` into an amount field and saves
- **THEN** the field either interprets it as 1.5 or refuses the save, and does
  not submit `null`

#### Scenario: A quantity keeps its precision

- **WHEN** a line's quantity is stored as `0.2500`
- **THEN** the field shows `0.25` and saving without editing it does not change
  the stored value

#### Scenario: The invoice date is picked, not typed

- **WHEN** the reviewer opens the invoice date field
- **THEN** a calendar is presented, and choosing a day submits `YYYY-MM-DD`

### Requirement: Both invoice numbers are shown in their correct roles

The voucher panel SHALL present the number printed on the document as the
invoice's number, and the ERP's as-posted number as metadata.

- The editable "Invoice number" field SHALL bind to `document_invoice_number`.
- The as-posted `invoice_number` SHALL be shown in the panel's leading metadata
  block, as read-only evidence, labelled so it is not mistaken for the
  supplier's number.
- When the two disagree, both SHALL remain visible. A disagreement means the
  ERP's number is wrong or the scan belongs to another invoice, and either is
  worth seeing.
- When the document states no number, the field SHALL be empty and offered for a
  reviewer to fill, not silently backfilled from the ERP's value.

#### Scenario: The printed number is the editable one

- **WHEN** a manager opens the Details tab
- **THEN** the "Invoice number" field holds `document_invoice_number` and editing
  it corrects that field

#### Scenario: The posted number is metadata

- **WHEN** the panel is open
- **THEN** the ERP's `invoice_number` appears in the metadata block as
  non-editable text

#### Scenario: A missing printed number is not backfilled

- **WHEN** an invoice has a null `document_invoice_number` and a posted one
- **THEN** the editable field is empty and the posted number appears only as
  metadata
