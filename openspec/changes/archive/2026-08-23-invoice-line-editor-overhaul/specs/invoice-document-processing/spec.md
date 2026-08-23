## ADDED Requirements

### Requirement: Extraction reads an item name distinct from the description

The document extractor SHALL return, per line, an item name and a description as
separate fields, and SHALL persist both.

- The item name is what was bought: the product or service as the document names
  it, without quantities, prices, dates or terms folded in.
- The description is any further prose the line printed. When the document states
  only one text, that text SHALL be the **item name** and the description SHALL
  be null — the name is the field every line is expected to carry.
- The model SHALL NOT invent a name. A line whose text cannot be read yields a
  null item name, on the same rule that an unreadable amount yields no amount
  rather than a guess.
- Neither field SHALL be required on a per-page reading. A page is a fragment,
  and a whole-invoice requirement applied to one page throws away a correct
  partial reading.

#### Scenario: A document stating both yields both

- **WHEN** a line reads "Figma Organization seat — annual plan, billed yearly"
  and the extractor separates them
- **THEN** the stored line has that item name and that description

#### Scenario: A document stating one text names the item

- **WHEN** a line's only text is "Cloudflare Pro subscription"
- **THEN** the stored line's `item_name` is that text and its `description` is
  null

#### Scenario: An unreadable line names nothing

- **WHEN** a line's text cannot be read from the page
- **THEN** `item_name` is null rather than a fabricated or partial value

#### Scenario: Replacement audits the item name it removed

- **WHEN** an extraction replaces existing lines
- **THEN** each removed line's `superseded_by_extraction` audit row carries its
  item name

### Requirement: Extraction stores the number it read as the document's number

The invoice number an extraction reads SHALL be stored as
`document_invoice_number` and SHALL NOT be written to `invoice_number`.

This restates an existing constraint because the field is becoming correctable:
once a human can edit it, the guarantee that extraction writes only the document
column is what keeps a later re-read from overwriting the ledger's own value.

A re-extraction SHALL respect the invoice's `verified_fields`: a
`document_invoice_number` a human has settled SHALL NOT be overwritten by a
subsequent extraction.

#### Scenario: A re-read does not overwrite a settled number

- **WHEN** an invoice whose `document_invoice_number` a human corrected is
  reprocessed and the model reads the original misprint again
- **THEN** the human's value stands

#### Scenario: A re-read fills an unsettled number

- **WHEN** an invoice whose `document_invoice_number` no human has touched is
  reprocessed
- **THEN** the newly read number replaces the previous one
