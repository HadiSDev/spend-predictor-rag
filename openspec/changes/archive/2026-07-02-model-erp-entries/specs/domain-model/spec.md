## ADDED Requirements

### Requirement: Invoice carries the internal file reference and no voucher

An `Invoice` SHALL record the internal File reference for the scanned document and SHALL NOT store the ERP voucher id (an `Invoice` is an invoice scan: the digitized supplier document and its line items; the voucher belongs to `ErpEntry`).

- `Invoice` SHALL have a nullable `file_id` (FK → `files`) — the reference into
  the internal File domain for the stored scan document. It is NULL when no scan
  file is available (e.g. purely synthetic data with no rendered document).
- `Invoice` SHALL NOT have a `voucher_id` column; the voucher is recorded on
  `ErpEntry`, and the entry→invoice association is resolved at ingest, not stored
  on the invoice.
- `file_id` is distinct from `erp_id`/`invoice_number`; those fields keep the
  native invoice number and SHALL NOT be overloaded to carry the voucher.

#### Scenario: Invoice records its scan file, not a voucher

- **WHEN** an invoice scan is imported for a voucher that has an attached document
- **THEN** the persisted `Invoice` has `file_id` set to the internal `files` row
  for the scan and exposes no voucher field

#### Scenario: Missing scan document leaves file reference null

- **WHEN** an invoice scan is imported for a voucher that has no attached
  document file
- **THEN** the persisted `Invoice` has `file_id` NULL and import still succeeds

### Requirement: Entries resolve to at most one invoice scan via the voucher

`ErpEntry` records SHALL relate to invoice scans as **many entries → one
invoice**, resolved through the shared voucher. A single voucher may post several
entries (net, VAT, rounding, split accounts); all of them SHALL point at the one
`Invoice` scan for that voucher.

- `ErpEntry` SHALL have a `voucher_id` (text) column recording the voucher of the
  posting it belongs to.
- When an invoice scan exists for an entry's voucher, the entry's
  `source_invoice_id` SHALL be set to that invoice. The match is resolved from the
  voucher at ingest; the invoice itself does not store the voucher.
- An entry whose voucher has no invoice scan (journal entry, payment, credit note
  with no scanned document) SHALL be persisted with `source_invoice_id` NULL.
- No `Invoice` field is derived by summing entries in this change; the invoice
  scan totals come from the scan payload, and entries are stored as raw financial
  context alongside it.

#### Scenario: Multiple entries link to one invoice scan

- **WHEN** a voucher for a purchase invoice posts three entries (net, VAT,
  rounding) and its invoice scan is imported
- **THEN** all three `ErpEntry` rows share the same `voucher_id` and have
  `source_invoice_id` pointing at the same `Invoice`, which stores no voucher

#### Scenario: Non-invoice entry has no source invoice

- **WHEN** an entry belongs to a voucher that has no invoice scan (e.g. a payment)
- **THEN** the `ErpEntry` row is persisted with `source_invoice_id` NULL

### Requirement: Categorization scope remains invoices and invoice lines

AI categorization SHALL continue to operate only on `Invoice` and `InvoiceLine`.
Adding entry ingestion SHALL NOT cause `ErpEntry` rows to be categorized by the
sync pipeline; entries are persisted as raw financial context only.

#### Scenario: Entries are not categorized on import

- **WHEN** the sync pipeline persists entries and then runs categorization
- **THEN** only `InvoiceLine` rows are categorized, and `ErpEntry` rows retain
  their default `status` with categorization fields unset
