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

## MODIFIED Requirements

### Requirement: ErpAccount has a sync-selection toggle distinct from ERP active state

`ErpAccount` SHALL carry a `sync_enabled` boolean that WE own, controlling whether the sync pulls entries for that account, and it SHALL be distinct from `is_active` (which mirrors the ERP's own active/inactive state).

- `sync_enabled` SHALL default to `true` so a first sync behaves as before.
- `sync_enabled` SHALL be preserved across re-syncs — refreshing an account's
  metadata from the ERP MUST NOT reset a user's selection.
- `is_active` SHALL continue to reflect the ERP's active flag and MUST NOT be
  overloaded as the sync toggle.
- `sync_enabled` is scoped per `ErpAccount`, i.e. per `ErpIntegration` per Company.
- Disabling an account SHALL NOT delete entries already persisted for it. The
  history is retained.
- Disabling an account SHALL, however, **hide** its entries from the entry
  listings. An account is enabled when first discovered, so anything pulled
  before a customer narrowed their selection stays in the database; leaving it
  visible contradicts the setting that says the account is not part of their
  spend picture. Hiding rather than deleting is what makes the toggle
  reversible — re-enabling an account brings its history straight back.
- The toggle SHALL govern *listings*, not lookup by id, exactly as the
  excluded-entry-type rule does.

#### Scenario: Disabled account is excluded from entry ingestion

- **WHEN** an `ErpAccount` has `sync_enabled = false`
- **THEN** the sync does not fetch or persist any `ErpEntry` for that account

#### Scenario: Selection survives a re-sync

- **WHEN** an account is toggled `sync_enabled = false` and the ERP accounts are
  fetched again on the next sync
- **THEN** the account's `sync_enabled` stays `false` while its name, type and
  parent metadata are refreshed

#### Scenario: Disabling an account leaves its history intact but unlisted

- **WHEN** an account with already-synced entries is set to `sync_enabled = false`
- **THEN** its existing `ErpEntry` rows remain in the database, future ingestion
  stops, and those rows no longer appear in the entry listings

#### Scenario: Re-enabling an account restores its entries

- **WHEN** a deselected account with retained history is set back to
  `sync_enabled = true`
- **THEN** its existing entries appear in the listings again, with no re-sync
