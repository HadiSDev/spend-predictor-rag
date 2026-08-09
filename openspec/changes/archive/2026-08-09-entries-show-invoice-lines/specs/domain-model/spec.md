## ADDED Requirements

### Requirement: InvoiceLine records where it came from

`InvoiceLine` SHALL carry a non-null `origin` of `erp`, `document_ai`, or
`entry_fallback`, recording which source produced the line.

- `erp` — the ERP supplied the line itself (a bill line on the voucher).
- `document_ai` — our AI extracted the line from the invoice's attached document.
- `entry_fallback` — no document extraction was available, so the line stands in
  for one expense posting on the voucher.
- Precedence between sources SHALL be `document_ai` > `erp` > `entry_fallback`.
  The document is the only source that knows what was actually bought; the ERP's
  own lines are its statement of the same voucher; a posting is the last resort.
- `origin` SHALL be a property of the line and SHALL NOT be inferred from its
  values at read time. A stand-in line and an extracted line can carry identical
  descriptions and amounts, and the difference — whether anyone has read the
  document — is exactly what a reader needs to know.
- An invoice SHALL NOT hold lines of more than one origin at a time. Two origins
  describe the same spend twice and its total would be double-counted.
- Existing rows SHALL be backfilled to `erp`, which is what every line written
  before this change was.

#### Scenario: A line states its source

- **WHEN** a line is read back
- **THEN** it carries an `origin` of `erp`, `document_ai` or `entry_fallback`

#### Scenario: A stand-in and an extracted line are distinguishable

- **WHEN** a stand-in line and an extracted line carry the same description and
  amount
- **THEN** they are still told apart by `origin`

#### Scenario: One origin per invoice

- **WHEN** an invoice's lines are listed
- **THEN** every line shares the same `origin`

### Requirement: InvoiceLine records its position on the invoice

`InvoiceLine` SHALL carry a non-null `sequence` recording the position its
source stated it in, and every reader SHALL order an invoice's lines by it.

- A line's `id` is a random UUID, so ordering by it alone presents a document's
  lines in an arbitrary sequence. That was invisible while the Entries page
  listed postings; it is wrong the moment the page lists lines, because an
  invoice reads top to bottom and its lines are no longer interchangeable rows.
- The writers SHALL set it from the order their source gave: the ERP's line
  order, the document's line order, or the posting order for stand-ins.
- `id` SHALL remain the tiebreak, so the order is total and deterministic even
  where two lines share a sequence.
- Existing rows SHALL be backfilled to `0`, which leaves their relative order
  exactly as it was.

#### Scenario: Lines read in the order their source stated them

- **WHEN** a document's three lines are extracted and the invoice is read back
- **THEN** they come back in the document's order, not in id order

#### Scenario: The order is total

- **WHEN** two lines share a `sequence`
- **THEN** they are still returned in a stable order on every request

### Requirement: InvoiceLine records the unit its quantity is counted in

`InvoiceLine` SHALL carry a nullable `unit` — the unit of measure the line's
`quantity` is expressed in (`pcs`, `hours`, `kg`, `months`).

- A bare quantity is ambiguous: `12` against "Consulting" is twelve hours or
  twelve days or twelve engagements, and a spend tool that compares unit prices
  across suppliers cannot compare them without it.
- It SHALL be taken from whichever source stated it, and SHALL be null when none
  did. Null is the ordinary case: an ERP's bill line states an account and an
  amount, not a unit of measure — Billy's carries `quantity` with no unit field
  at all — and a posting has neither. Only the document reliably names one.
- It SHALL NOT be inferred from the description, and no default SHALL be
  substituted. "pcs" assumed over an hourly consulting line is a wrong figure
  presented with confidence.

#### Scenario: An extracted line carries its unit

- **WHEN** a document states "12 hours" on a line and it is extracted
- **THEN** the line's `quantity` is 12 and its `unit` is `hours`

#### Scenario: An ERP line that names no unit stores none

- **WHEN** a Billy bill line with `quantity: 1` and no unit field is synced
- **THEN** the line's `unit` is null rather than a substituted default

#### Scenario: A stand-in line has no unit

- **WHEN** a posting stands in for a line
- **THEN** its `unit` is null

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

### Requirement: Invoice records its document-processing state

`Invoice` SHALL carry `doc_status`, `doc_attempts`, `doc_error` and
`doc_processed_at` describing whether its attached document has been turned into
lines.

- `doc_status` SHALL be one of `not_applicable`, `pending`, `processing`,
  `processed`, `failed`.
- These fields SHALL be distinct from `Invoice.status`, which remains the
  categorization rollup of the invoice's lines. One says whether we have read the
  document; the other says whether the resulting spend has been categorized and
  verified. Conflating them would make an invoice with no scan look uncategorized
  and a categorized invoice look processed.
- Existing rows SHALL be backfilled to `not_applicable` where no file is
  attached and `pending` where one is, so the first stage run picks up the
  backlog without a separate migration step.

#### Scenario: The two statuses are independent

- **WHEN** an invoice's document extraction fails but its stand-in lines are all
  categorized
- **THEN** its `doc_status` is `failed` and its `status` is `categorized`

#### Scenario: Existing invoices with a scan are queued by the migration

- **WHEN** the migration runs over invoices that already carry a `file_id`
- **THEN** those invoices read `pending` and the rest read `not_applicable`
