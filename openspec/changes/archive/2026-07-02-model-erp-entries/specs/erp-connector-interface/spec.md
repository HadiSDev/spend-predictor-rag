## ADDED Requirements

### Requirement: Connector fetches entries as the primary ledger unit

The `ErpConnector` interface SHALL expose `fetch_entries(since: date | None) ->
list[ErpEntryData]` returning normalized GL postings. Entries are the atomic
financial records real ERPs expose; every implementation SHALL provide this
method.

`ErpEntryData` SHALL be a normalized DTO carrying at least:

- `erp_entry_id` (native entry id), `voucher_id` (the voucher this posting
  belongs to), `entry_type` (e.g. `purchase_invoice`, `journal_entry`,
  `payment`, `credit_note`)
- `erp_account_code` (native account), `entry_date`, `description`
- `debit_amount`, `credit_amount`, `currency`
- `raw` (original ERP record)

`since` SHALL filter entries incrementally by posting date when supplied.

#### Scenario: fetch_entries returns voucher-tagged postings

- **WHEN** `fetch_entries()` is called against a connected ERP
- **THEN** it returns `ErpEntryData` records each carrying a `voucher_id` and its
  native account code, debit/credit amounts, and entry type

#### Scenario: Incremental entry fetch honors the watermark

- **WHEN** `fetch_entries(since=D)` is called
- **THEN** only entries with an entry date on or after `D` are returned

### Requirement: Invoice scans are retrieved per voucher

Invoice scans (line items plus the attached document reference) SHALL be
retrievable **per voucher** rather than only as a flat invoice list, because in
the real ERP the scan is a separate resource keyed by the voucher that its
entries carry.

- The connector SHALL provide a way to obtain the invoice scan for a given
  voucher (e.g. `fetch_invoice_scan(voucher_id) -> ErpInvoiceData | None`),
  returning `None` when the voucher has no scan.
- `ErpInvoiceData` SHALL expose the `voucher_id` it corresponds to and, when
  present, a reference to the attached scan document (filename / storage key /
  content) sufficient for the runner to record a `File`.

#### Scenario: Scan fetched for an invoice-bearing voucher

- **WHEN** entries reference voucher V whose `entry_type` is `purchase_invoice`
- **THEN** the connector can return the `ErpInvoiceData` scan for V, including its
  lines and attached-document reference

#### Scenario: Voucher without a scan yields no invoice

- **WHEN** the invoice scan for a voucher is requested but the voucher has no
  scanned document (e.g. a payment voucher)
- **THEN** the connector returns `None` and no `Invoice` is created for it

### Requirement: Sync runner ingests entries before invoice scans

The sync-runner integration SHALL follow an entry-first ordering: fetch entries,
group them by voucher, fetch and persist the invoice scan (with lines and file)
for invoice-bearing vouchers, then persist entries linked to the matching
invoice via `source_invoice_id`.

#### Scenario: Runner links persisted entries to their invoice scan

- **WHEN** a sync run processes a voucher with a purchase-invoice scan and several
  entries
- **THEN** the invoice scan and its lines are persisted first, and each entry is
  persisted with `source_invoice_id` pointing at that invoice
