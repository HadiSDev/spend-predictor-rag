## ADDED Requirements

### Requirement: Line payloads carry the item name

Every invoice-line payload the API returns SHALL carry `item_name` alongside
`description`, both nullable.

A client SHALL NOT have to infer which of the two is the line's label: both are
present, and the presentation rule (name first, description as fallback) is the
client's to apply because only the client knows how much room it has.

#### Scenario: A line lists both fields

- **WHEN** a line with an item name and a description is read
- **THEN** the payload carries both under their own keys

#### Scenario: A line with no name still carries the key

- **WHEN** a line has a null `item_name`
- **THEN** the payload carries `item_name: null` rather than omitting the key

### Requirement: A human may correct a line's item name

`PATCH /invoice-lines/{id}` SHALL accept `item_name` as a correctable value
field, on the same terms as `description`.

- Correcting it SHALL mark it in the line's `verified_fields`, so a later sync
  does not overwrite it.
- The correction SHALL be audited with its previous value.
- Clearing it SHALL be permitted (an explicit null), because a reviewer splitting
  a stand-in line may legitimately have nothing to name.

#### Scenario: The item name is corrected

- **WHEN** a manager sends `item_name` on a line
- **THEN** the stored value changes, `item_name` is marked verified, and an audit
  row records the previous value

#### Scenario: A corrected item name survives a sync

- **WHEN** a sync re-persists a line whose `item_name` a human corrected
- **THEN** the corrected value is left in place

#### Scenario: The item name is not a category

- **WHEN** a caller sends a categorization field alongside `item_name`
- **THEN** the request is refused with 422, exactly as it is today

### Requirement: A human may correct the number printed on the document

`PATCH /invoices/{id}` SHALL accept `document_invoice_number`, and
`POST /invoices/{id}/verify` SHALL accept it as a field a human can assert.

- The correction SHALL be audited with its previous value. This is required, not
  optional: the correction is applied in place and there is no shadow column
  holding what the extractor read.
- Correcting it SHALL NOT alter `invoice_number`.
- Correcting it SHALL NOT clear the invoice's base-currency figures — unlike
  `currency`, `total` and `tax`, an invoice number is not an input to any
  conversion.

#### Scenario: The printed number is corrected

- **WHEN** a manager sends `document_invoice_number` on an invoice
- **THEN** the stored value changes and an audit row records the previous one

#### Scenario: The posted number is untouched

- **WHEN** `document_invoice_number` is corrected
- **THEN** `invoice_number` is unchanged

#### Scenario: FX figures survive an invoice-number correction

- **WHEN** a converted invoice's `document_invoice_number` is corrected
- **THEN** its `base_total`, `base_tax`, `fx_rate` and `fx_rate_date` are
  unchanged
