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
