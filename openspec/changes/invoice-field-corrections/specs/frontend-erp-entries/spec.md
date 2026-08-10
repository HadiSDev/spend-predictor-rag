## MODIFIED Requirements

### Requirement: An entry's full detail opens in a side drawer

Activating a voucher row, or a line within it, SHALL open the URL-addressable voucher panel beside the table, which SHALL carry a **Lines** tab and a **Postings** tab in addition to its existing tabs, with the table remaining in place behind it. The panel SHALL be dismissable by escape, by its close control, and by activating outside it.

- The **Lines** tab SHALL list the voucher's invoice lines with their
  categorization, and SHALL be where a line's category **and its description,
  quantity, unit, unit price and amount** are corrected. It is the tab that opens
  when a line is activated from the expanded table. It SHALL also be where a line
  is added to the invoice or deleted from it.
- The **Postings** tab SHALL list every `ErpEntry` of the voucher — expense,
  VAT, liability, asset and income alike — each with its account code and name,
  entry type, accounting date, description, debit, credit, status, any error
  message, and the ERP's own entry identifier. It SHALL NOT filter by account
  type: a balanced voucher's postings sum to zero, which is what a general
  ledger shows.
- Postings SHALL be presented as flat evidence text, never as disabled inputs.
  They are ERP-posted values and nothing about them is correctable here. This
  applies to postings only: an invoice header and its lines are the pipeline's
  reading of the document and are corrected on their own tabs.
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

#### Scenario: Lines are editable

- **WHEN** a manager opens the Lines tab
- **THEN** each line's description, quantity, unit, unit price and amount are
  focusable inputs alongside its category selector

#### Scenario: The open tab is linkable

- **WHEN** a link carrying the postings tab is opened
- **THEN** the panel opens on the Postings tab

#### Scenario: The drawer is dismissable

- **WHEN** the user presses escape or activates the close control
- **THEN** the panel closes and focus returns to the row that opened it

## ADDED Requirements

### Requirement: The header editor is shown for every invoice

The Details tab SHALL render the invoice header as editable inputs regardless of
the invoice's `source`, for a caller with a management role.

- The editable fields SHALL be invoice number, invoice date, currency, total, tax
  and the supplier (name, country, VAT number), plus which vendor the invoice
  points at.
- A caller without a management role SHALL see the same values as flat text on a
  tinted surface, never as disabled inputs.
- The provenance badge SHALL remain, because where a value came from still tells
  the reviewer how much to trust it — it no longer decides whether it can be
  corrected.
- The editor SHALL keep its existing dirty-state discipline: Save and Cancel are
  disabled until a value moves, the saved baseline updates on success without
  waiting for a refetch, and unsaved edits are reported up so the drawer can
  guard dismissal.

#### Scenario: An ERP invoice's header is editable

- **WHEN** a manager opens the Details tab of an invoice with source `erp`
- **THEN** the header fields are focusable inputs and Save is available once a
  value changes

#### Scenario: A viewer sees evidence, not inputs

- **WHEN** a `viewer` opens the Details tab
- **THEN** the header values are rendered as text with no inputs at all

#### Scenario: Provenance is still shown

- **WHEN** the Details tab is rendered for an ERP-sourced invoice
- **THEN** the provenance badge reads that the header was posted by the ERP

### Requirement: The supplier is chosen, and its details annotated

The header editor SHALL let a reviewer pick which vendor the invoice points at
from the organization's referenced suppliers, and separately correct the
supplier's name, country and VAT number for this invoice alone.

- The vendor picker SHALL be a searchable selector over `GET /vendors`, not a
  free-text field, so the invoice points at a real catalog row.
- The country SHALL be chosen from the existing country list rather than typed.
- The editor SHALL make clear that name/country/VAT corrections apply to this
  invoice and do not change the supplier for anyone else.
- A field carrying an override SHALL be visibly marked as corrected, with the
  catalog's value reachable, so a reader can tell the two apart.

#### Scenario: Picking a different supplier

- **WHEN** a manager searches the vendor picker and selects another supplier
- **THEN** the invoice is saved pointing at that vendor

#### Scenario: An override is marked

- **WHEN** an invoice carries a supplier country override
- **THEN** the field is marked as corrected and the catalog's value is reachable

#### Scenario: The scope of an override is stated

- **WHEN** the supplier detail fields are rendered
- **THEN** the editor states that the correction applies to this invoice only

### Requirement: A line can be added or removed from the voucher panel

The Lines tab SHALL offer adding a line and deleting one, for a management role.

- Adding SHALL append an empty line the reviewer then fills in, marked as
  human-added.
- Deleting SHALL require an explicit confirmation naming what is being deleted,
  since a line carries a categorization a human may have verified.
- After either, the panel SHALL reflect the new line set and the voucher's
  reconciliation state without a manual reload.
- A human-added line SHALL be marked in the same way a provisional line is —
  text plus a mark, never colour alone.

#### Scenario: Splitting a stand-in line

- **WHEN** a manager adds two lines and deletes the stand-in
- **THEN** the tab shows the two new lines, each marked as human-added, and the
  stand-in is gone

#### Scenario: Deleting asks first

- **WHEN** a manager activates delete on a line
- **THEN** a confirmation naming the line is shown before anything is sent

#### Scenario: A viewer has neither control

- **WHEN** a `viewer` opens the Lines tab
- **THEN** neither the add nor the delete control is rendered

### Requirement: A voucher whose lines do not sum to its total says so

The voucher panel SHALL show a persistent warning carrying the delta whenever the
server reports an invoice's lines as not reconciled, and SHALL NOT block saving.

- The warning SHALL name both figures — the lines' sum and the invoice total —
  and the signed difference, so the reviewer can see which way it is out.
- It SHALL appear on the Lines tab, where the correction is made, and SHALL be
  visible from the panel header so it is not missed by a reviewer on another tab.
- It SHALL disappear as soon as the corrections bring the lines back within
  tolerance.

#### Scenario: A mismatch is warned, not blocked

- **WHEN** a manager corrects one line so the lines no longer sum to the total
- **THEN** the save succeeds and a warning shows the lines' sum, the total and
  the difference

#### Scenario: The warning clears

- **WHEN** the remaining lines are corrected so they sum to the total
- **THEN** the warning is gone

#### Scenario: The warning is visible from another tab

- **WHEN** a voucher's lines do not reconcile and the panel is on the Details tab
- **THEN** the mismatch is indicated in the panel header

### Requirement: An invoice header can be verified from the panel

The Details tab SHALL offer a verify action that marks the header as reviewed,
distinct from saving a correction.

- Verifying SHALL be available whether or not the reviewer changed anything —
  accepting the parsed values is itself the signal the AI needs.
- The panel SHALL show that the header is verified, by whom and when.
- The action SHALL be management-gated and absent for a read-only role.

#### Scenario: Accepting the parse

- **WHEN** a manager activates verify without editing anything
- **THEN** the header is marked verified and shows the verifier and time

#### Scenario: Verify after correcting

- **WHEN** a manager corrects the total and then verifies
- **THEN** both the correction and the verification are applied

#### Scenario: A viewer cannot verify

- **WHEN** a `viewer` opens the Details tab
- **THEN** no verify control is rendered
