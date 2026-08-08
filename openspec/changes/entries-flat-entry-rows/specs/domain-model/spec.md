## ADDED Requirements

### Requirement: Entries link to the invoice line they were posted from

`ErpEntry` SHALL carry a nullable `source_invoice_line_id` foreign key to
`InvoiceLine`, relating the two as **many entries → one line**. A single invoice
line may be posted across several accounts, so the link points from the posting
to the line and never the other way; `InvoiceLine` gains no reference back.

- The column SHALL be nullable, and NULL SHALL be the ordinary case rather than
  a defect. Input VAT, the accounts-payable counterparty, journal entries and
  payments are properties of a whole voucher and have no line behind them.
- The link SHALL be set only when the connector states which line a posting came
  from (`ErpEntryData.source_line_erp_id`). It SHALL NOT be inferred by matching
  on amount, account or description — an ERP that nets several lines into one
  posting would make any such guess silently wrong.
- The linked line SHALL be resolved by *deriving* its id from the same
  `(invoice, line_erp_id)` pair the invoice persistence uses, so the two agree by
  construction rather than by resemblance.
- A posting naming a line its invoice scan did not deliver SHALL be persisted
  with the link NULL rather than aborting the sync on a dangling key.
- `ErpEntry` SHALL still carry no categorization of its own. This link exists so
  that a posting can be read against the line whose category applies to it; the
  categorization remains the line's.

#### Scenario: A posting is linked to its line

- **WHEN** a connector reports a posting carrying the ERP's line id, and that
  invoice line was imported with the voucher's scan
- **THEN** the `ErpEntry` row's `source_invoice_line_id` points at that
  `InvoiceLine`

#### Scenario: Several postings share one line

- **WHEN** one invoice line is posted as more than one entry
- **THEN** every one of those entries points at the same `InvoiceLine`, and the
  line stores no reference back to them

#### Scenario: A posting with no line behind it

- **WHEN** an input-VAT, payable, or journal-entry posting is persisted
- **THEN** its `source_invoice_line_id` is NULL

#### Scenario: A dangling line reference does not fail the sync

- **WHEN** a connector names a line id that the invoice scan never delivered
- **THEN** the entry is persisted with `source_invoice_line_id` NULL and the sync
  continues
