## ADDED Requirements

### Requirement: Entries endpoint exposes voucher-tagged postings

The mock ERP API SHALL expose `GET /api/v1/entries` returning paginated GL
postings that mirror the real entry-first shape, so the connector's
`fetch_entries` can be exercised end-to-end deterministically.

- Each entry item SHALL carry a native entry id, a `voucherId`, an `entryType`
  (`purchase_invoice` | `journal_entry` | `payment` | `credit_note`), a
  reference to its native account, `entryDate`, `description`, and debit/credit
  amounts with currency.
- The endpoint SHALL support the existing pagination contract
  (`?page=&pageSize=`, `collection` + `pagination`) and an optional `since` date
  filter.
- For every generated purchase invoice, the entries whose `voucherId` matches the
  invoice's voucher SHALL sum consistently with that invoice (net + VAT), so
  entry data and invoice data are mutually reconcilable.

#### Scenario: List entries with pagination

- **WHEN** a client calls `GET /api/v1/entries?page=1&pageSize=100`
- **THEN** the response contains a `collection` of voucher-tagged entries and a
  `pagination` block, consistent with the other list endpoints

#### Scenario: Entries reconcile with their invoice

- **WHEN** a purchase invoice with voucher V is generated
- **THEN** `GET /api/v1/entries` includes entries tagged with `voucherId` V whose
  amounts reconcile with that invoice's net and VAT

### Requirement: Purchase invoices expose voucher id and attached file

Purchase-invoice payloads SHALL expose the `voucherId` they were posted under and
a reference to their attached scan document, so the connector can resolve the scan
per voucher and the runner can create the linked `File`. (The `voucherId` is used
to associate entries with the scan; it is stored on `ErpEntry`, not on the
`Invoice`.)

- Each purchase-invoice item SHALL include a `voucherId` matching the voucher of
  its corresponding entries.
- Each purchase-invoice item SHALL include an attached-file reference (e.g.
  filename and a storage key or download path) representing the scanned document.

#### Scenario: Invoice payload includes voucher and file reference

- **WHEN** a client fetches a purchase invoice from the mock ERP
- **THEN** the payload includes a `voucherId` and an attached-file reference for
  the scanned document

#### Scenario: Invoice voucher matches its entries

- **WHEN** a purchase invoice and its entries are generated for the same document
- **THEN** the invoice's `voucherId` equals the `voucherId` on those entries
