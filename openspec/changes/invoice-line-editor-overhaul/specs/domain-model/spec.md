## ADDED Requirements

### Requirement: InvoiceLine names what was bought, beside describing it

`InvoiceLine` SHALL carry a nullable `item_name` — the name of the product or
service on the line — **beside** its existing `description`.

The two are different statements and were being made by one field:

- `item_name` is what was bought. It is short, expected on every line, and it is
  the value a redundancy or savings comparison is actually about: "Figma
  Organization seat" is comparable across suppliers in a way that a sentence of
  prose is not.
- `description` is supplementary prose the supplier printed. It is frequently
  absent, and nothing downstream may assume it is present.

Constraints:

- `item_name` SHALL be nullable in the schema. A posting-derived stand-in line
  is built from a ledger memo that is itself frequently null, and a NOT NULL
  column would force the sync to invent a name.
- A reader SHALL be shown `item_name` as the line's primary label, falling back
  to `description` only when `item_name` is null.
- Both SHALL be correctable by a human, and both SHALL be recoverable from the
  audit log after correction.
- Existing rows SHALL be migrated: the stored `description` becomes `item_name`
  and `description` becomes null, because the single field was in practice
  holding the name.

#### Scenario: A line carries both

- **WHEN** a document states the item "Figma Organization seat" and the
  description "Annual plan, 12 seats, billed yearly"
- **THEN** the line's `item_name` is "Figma Organization seat" and its
  `description` is "Annual plan, 12 seats, billed yearly"

#### Scenario: A description-less line is still named

- **WHEN** a document states an item name and no further prose
- **THEN** `item_name` is set and `description` is null

#### Scenario: A stand-in line with no memo names nothing

- **WHEN** a stand-in line is written from a posting whose description is null
- **THEN** `item_name` is null rather than a fabricated value

#### Scenario: Migration moves the existing text into the name

- **WHEN** a line stored before this change holds the description "Cloudflare
  Pro subscription"
- **THEN** after migration its `item_name` is "Cloudflare Pro subscription" and
  its `description` is null

#### Scenario: Migration carries a human's settled field with the value

- **WHEN** a line whose `verified_fields` contains `description` is migrated
- **THEN** its `verified_fields` contains `item_name` and no longer contains
  `description`, so a sync still cannot overwrite the value a human settled

## MODIFIED Requirements

### Requirement: Invoice records the number printed on the document

`Invoice` SHALL carry a nullable `document_invoice_number` — the supplier's
invoice number as read from the attached document — **beside** the as-posted
`invoice_number`, which SHALL NEVER be rewritten by extraction.

- The as-posted value is frequently not an invoice number at all. Billy's
  `suppliersInvoiceNo` is user-entered and often null, and `voucherNo` is blank
  at least as often, so the connector falls back to the **bill id** — an
  internal identifier presented in a field the reader takes for the supplier's
  number. The number printed on the invoice is the one a human reconciles
  against, and only the document has it.
- The two SHALL be stored separately for the same reason `base_total` sits
  beside `total` rather than replacing it: the as-posted column is the evidence,
  and overwriting it would destroy the record of what the ERP actually holds and
  make the two impossible to compare.
- A reader SHALL be shown the document's number in preference to the as-posted
  one, and SHALL be able to see both when they disagree — a disagreement is
  information (the ERP's is wrong, or the scan is of a different invoice), not
  noise to resolve silently.
- Extraction SHALL leave it null rather than guess when the document states no
  number.
- **`document_invoice_number` SHALL be correctable by a human**, and its original
  value SHALL be recoverable from the audit log. It is a value a model read off a
  scan, and a misread digit is exactly the kind of error a reviewer is there to
  fix.
- `invoice_number` SHALL remain the as-posted evidence. Its correctability
  through the API is unchanged by this requirement; what changes is that it is no
  longer the field a reviewer is *presented* with, since the number worth
  reconciling against is the printed one.

#### Scenario: The printed number is stored beside the posted one

- **WHEN** a bill whose `invoice_number` fell back to the bill id is extracted
  and the document reads "2026-0412"
- **THEN** `document_invoice_number` is "2026-0412" and `invoice_number` still
  holds the bill id

#### Scenario: Extraction never rewrites the posted number

- **WHEN** an invoice is extracted
- **THEN** its `invoice_number` is exactly what it was before

#### Scenario: A document that states no number stores none

- **WHEN** the extraction yields no invoice number
- **THEN** `document_invoice_number` is null

#### Scenario: A misread printed number is corrected

- **WHEN** a reviewer corrects `document_invoice_number` from "2026-04I2" to
  "2026-0412"
- **THEN** the stored value is the correction and the audit log holds the
  original

#### Scenario: The posted number stays as the ERP stated it

- **WHEN** a reviewer corrects the printed number on an invoice whose
  `invoice_number` fell back to the bill id
- **THEN** `invoice_number` still holds the bill id, unchanged
