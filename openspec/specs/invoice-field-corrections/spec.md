# invoice-field-corrections Specification

## Purpose
TBD - created by archiving change invoice-field-corrections. Update Purpose after archive.
## Requirements
### Requirement: Every parsed invoice field is correctable, regardless of provenance

A human with a management role SHALL be able to correct an invoice's header
fields and its lines' descriptive and money fields, whether the invoice was
posted by the ERP or extracted from a document. Provenance SHALL NOT gate
correctability.

- Corrections SHALL be applied **in place**, over the stored value. There is no
  parallel corrected-value column set.
- Every field-level change SHALL be written to `AuditLog`, whose `old` value is
  the only record of what the ERP or the extractor originally stated.
- The correctable invoice fields SHALL be `invoice_number`, `invoice_date`,
  `currency`, `total`, `tax`, `vendor_id`, `supplier_name`,
  `supplier_country_code` and `supplier_vat_number`.
- The correctable line fields SHALL be `description`, `quantity`, `unit`,
  `unit_price` and `amount`, in addition to the categorization fields the verify
  endpoint already accepts.
- `native_account_code` SHALL NOT be correctable. It is the ledger's own
  statement of where the money was posted, and a value contradicting it
  reconciles against nothing.

#### Scenario: An ERP-sourced invoice can be corrected

- **WHEN** a manager corrects the total of an invoice whose `source` is `erp`
- **THEN** the stored total is the corrected value and the request succeeds

#### Scenario: The original value survives in the audit trail

- **WHEN** a manager changes an invoice's total from the ERP-posted figure
- **THEN** an `AuditLog` row records the field, the ERP's figure as `old`, and
  the corrected figure as `new`

#### Scenario: The posted account code is not correctable

- **WHEN** a correction names `native_account_code` on a line
- **THEN** the API rejects the request and the line is unchanged

#### Scenario: A read-only role cannot correct

- **WHEN** a `member` or `viewer` submits a correction
- **THEN** the API responds `403 Forbidden` and nothing is written

### Requirement: Verification is a distinct, recorded action

A human SHALL be able to verify an invoice header, marking the fields they have
settled, in the same shape line verification already takes.

- `POST /api/v1/invoices/{id}/verify` SHALL accept optional corrections, apply
  them, mark the header verified, append an `AuditLog` entry, and commit as one
  transaction.
- The action SHALL be recorded as `edit` when a value moved and `verify` when the
  human accepted the parsed values unchanged.
- The invoice SHALL record who verified it and when.
- Verification SHALL record **which fields** were settled, not merely that the
  invoice was reviewed, so a later sync can tell a settled field from an
  untouched one.
- A line's existing `POST /api/v1/invoice-lines/{id}/verify` SHALL likewise
  record which fields it settled.

#### Scenario: Accepting the parsed values

- **WHEN** a manager verifies an invoice with no corrections
- **THEN** the header is marked verified, the audit action is `verify`, and no
  field value changed

#### Scenario: Correcting during verification

- **WHEN** a manager verifies an invoice correcting its tax
- **THEN** the tax is stored, the audit action is `edit` with the tax diff, and
  `tax` is among the invoice's verified fields

#### Scenario: Verification is attributed

- **WHEN** a manager verifies an invoice
- **THEN** the invoice records that user as the verifier and the time of the
  verification, and the audit entry names the same actor

### Requirement: A verified field is never overwritten by an automated write

Once a human has settled a field, no automated process SHALL overwrite it.

- The sync runner SHALL refresh every field of an invoice and its ERP lines as it
  does today, **except** the fields recorded as verified, which it SHALL leave
  untouched.
- The runner SHALL provide one explicit escape hatch — a `--hard-reset` flag —
  which restores the ERP's values over human-settled ones. It SHALL be opt-in and
  SHALL never be the default.
- A `--hard-reset` overwrite SHALL be audited exactly as a human correction is,
  with actor `system`, so the settled value is recoverable.
- Automatic document processing SHALL NOT replace the lines of an invoice that
  carries human-verified lines. An explicit `POST /invoices/{id}/reprocess` is a
  human decision and SHALL proceed, replacing and auditing as it does today.

#### Scenario: A sync leaves a corrected total alone

- **WHEN** an invoice's `total` has been verified and the ERP is re-synced with a
  different total
- **THEN** the stored total remains the human's value, while unverified fields
  such as `raw_json` are refreshed

#### Scenario: A hard reset restores the ERP's value

- **WHEN** the sync runs with `--hard-reset` over an invoice with a verified
  total
- **THEN** the ERP's total is stored and an audit entry records the overwrite
  with actor `system`

#### Scenario: A new document does not silently discard verified lines

- **WHEN** a sync attaches a different document to an invoice whose lines include
  a verified one
- **THEN** the invoice is not queued for automatic replacement and its lines are
  unchanged

#### Scenario: An explicit reprocess still wins

- **WHEN** a manager calls `POST /invoices/{id}/reprocess` on an invoice with
  verified lines
- **THEN** the document is queued and, on success, the lines are replaced with an
  audit row per removed line

### Requirement: The supplier is correctable without mutating the shared catalog

A supplier correction made in one tenant SHALL NOT change what another tenant
sees, because `Vendor` is a global catalog row shared across organizations.

- An invoice SHALL be re-pointable at a different existing `Vendor` by
  `vendor_id`.
- An invoice SHALL carry its own `supplier_name`, `supplier_country_code` and
  `supplier_vat_number` overrides, which SHALL be stored on the invoice and SHALL
  NOT write through to the `Vendor` row.
- Invoice payloads SHALL expose the resolved supplier — the override when set,
  otherwise the linked vendor's value — alongside a marker that the value was
  overridden, so a reader can tell a corrected supplier from a catalogued one.
- `vendor_id` naming a vendor that does not exist SHALL be rejected with `422`.

#### Scenario: Correcting the country leaves the vendor untouched

- **WHEN** a manager sets an invoice's `supplier_country_code` to `DE` while its
  vendor's `country_code` is `DK`
- **THEN** the invoice resolves its supplier country as `DE`, the `Vendor` row
  still reads `DK`, and no other invoice referencing that vendor changes

#### Scenario: Re-pointing at another vendor

- **WHEN** a manager sets an invoice's `vendor_id` to another vendor in the
  catalog
- **THEN** the invoice reports the new vendor's name and the change is audited

#### Scenario: An unknown vendor is rejected

- **WHEN** a correction names a `vendor_id` that does not exist
- **THEN** the API responds `422 Unprocessable Entity` and the invoice is
  unchanged

#### Scenario: An override is distinguishable from the catalog value

- **WHEN** an invoice carries a supplier name override
- **THEN** its payload marks the supplier name as overridden

### Requirement: Lines can be added and deleted

A reviewer SHALL be able to add a line to an invoice and delete one, so a
stand-in line covering several purchases can be split into what was actually
bought.

- `POST /api/v1/invoices/{id}/lines` SHALL create a line on the invoice with the
  correctable line fields, at the caller's `sequence` or after the last line.
- A human-created line SHALL record its origin as `human`, which SHALL take
  precedence over `document_ai`, `erp` and `entry_fallback` — a sync or an
  extraction SHALL NOT displace it.
- `DELETE /api/v1/invoice-lines/{id}` SHALL remove the line, append an
  `AuditLog` entry carrying the deleted line's field values and categorization,
  and set `source_invoice_line_id` to NULL on every `ErpEntry` that referenced
  it — postings are evidence and SHALL NOT be deleted with the line.
- Adding or deleting a line SHALL recompute the invoice's status rollup in the
  same transaction.
- A human-added line SHALL move through the categorization lifecycle exactly as
  any other line: created `uncategorized`, categorizable, verifiable, and counted
  in the reports.

#### Scenario: Splitting a stand-in line

- **WHEN** a manager adds two lines to an `entry_fallback` invoice and deletes
  the stand-in
- **THEN** the invoice holds the two new lines, each with origin `human` and
  status `uncategorized`, and the rollup is recomputed

#### Scenario: A deleted line's values are recoverable

- **WHEN** a manager deletes a line that carried a verified category
- **THEN** an audit entry records the deletion with the line's description,
  amount and categorization

#### Scenario: Postings survive their line's deletion

- **WHEN** a line referenced by two postings is deleted
- **THEN** both postings remain, with `source_invoice_line_id` NULL

#### Scenario: A sync does not remove a human line

- **WHEN** an invoice with a human-added line is re-synced
- **THEN** the human line is still present and unchanged

### Requirement: A correction that breaks reconciliation warns and never blocks

When corrected lines no longer sum to the invoice's total, the API SHALL store
the correction and report the mismatch, rather than rejecting it.

- An invoice's lines SHALL be considered reconciled when they sum to the
  invoice's `total` **or** its `total − tax`, within the same tolerance the
  document stage applies (`max(1%, 1.00)`). The tolerance rule SHALL be shared
  code with the document stage, so the two cannot disagree.
- Invoice payloads SHALL carry whether the lines reconcile and, when they do not,
  the signed delta between the lines' sum and the nearest accepted total.
- A correction SHALL NOT be rejected for breaking reconciliation. A reviewer
  part-way through a multi-line fix must not be blocked by their own unfinished
  work, and the ERP's total may itself be the wrong figure.

#### Scenario: A mid-edit mismatch is saved

- **WHEN** a manager corrects one of three lines so the lines no longer sum to
  the invoice total
- **THEN** the correction is stored and the invoice payload reports the mismatch
  with the delta

#### Scenario: A finished multi-line fix reconciles again

- **WHEN** the manager corrects the remaining lines so they sum to the total
- **THEN** the invoice payload reports the lines as reconciled and carries no
  delta

#### Scenario: Tolerance matches the document stage

- **WHEN** the lines' sum differs from the total by less than the shared
  tolerance
- **THEN** the invoice is reported as reconciled

### Requirement: A correction that invalidates a conversion clears it

A correction to an amount a base-currency figure was derived from SHALL clear
that figure rather than recompute it inline.

- Correcting an invoice's `currency`, `total` or `tax` SHALL null that invoice's
  `base_currency`, `base_total`, `base_tax`, `fx_rate` and `fx_rate_date`.
- Correcting a line's `amount` SHALL null that line's `base_currency`,
  `base_amount`, `fx_rate` and `fx_rate_date`.
- The cleared fields SHALL appear in the same audit diff as the correction that
  caused them, so the trail shows the whole effect.
- No conversion SHALL be performed inline. `POST /companies/{id}/recompute-fx`
  restores the figures at each row's own historical rate.

#### Scenario: Correcting a line amount clears its conversion

- **WHEN** a manager corrects a converted line's `amount`
- **THEN** the line's base amount, rate and rate date are null and the audit
  entry shows both the amount change and the cleared conversion

#### Scenario: Correcting an unrelated field keeps the conversion

- **WHEN** a manager corrects only a line's `description`
- **THEN** the line's base amount and rate are unchanged

