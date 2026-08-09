## MODIFIED Requirements

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
  **Description**, **Quantity**, **Unit**, **Spend category**, **Amount** —
  because the table's header names the columns of a *voucher* row, not a line's.
  The line figure SHALL be headed **Amount**, not Total Spend.
- **Unit** SHALL be its own column beside Quantity, not appended to the quantity
  cell: the quantity is a right-aligned tabular figure meant to be scanned down,
  and a unit inside that cell breaks the alignment on every row that has one. An
  empty Unit cell SHALL read as empty rather than as a substituted default.
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
- **THEN** Description, Quantity, Unit, Spend category and Amount headers are
  shown above its lines

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
- **THEN** the voucher header row, the line header row and each line row span
  the same column count, so a line's figure sits under Amount

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

### Requirement: An entry's full detail opens in a side drawer

Activating a voucher row, or a line within it, SHALL open the URL-addressable voucher panel beside the table, which SHALL carry a **Lines** tab and a **Postings** tab in addition to its existing tabs, with the table remaining in place behind it. The panel SHALL be dismissable by escape, by its close control, and by activating outside it.

- The **Lines** tab SHALL list the voucher's invoice lines with their
  categorization, and SHALL be where a line's category is corrected. It is the
  tab that opens when a line is activated from the expanded table.
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
- **THEN** the voucher panel opens on its Lines tab with that line in view, and
  the table stays rendered behind it

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

## ADDED Requirements

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
