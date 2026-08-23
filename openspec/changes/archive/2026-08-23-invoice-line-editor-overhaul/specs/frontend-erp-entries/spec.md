## ADDED Requirements

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

## MODIFIED Requirements

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
