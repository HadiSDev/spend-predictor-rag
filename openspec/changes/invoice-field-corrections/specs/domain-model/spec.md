## ADDED Requirements

### Requirement: Invoice carries invoice-scoped supplier overrides

`Invoice` SHALL carry nullable `supplier_name`, `supplier_country_code` and
`supplier_vat_number` columns holding a human's correction of the supplier for
that invoice alone.

- They SHALL be null in the ordinary case, meaning "no correction — use the
  linked `Vendor`". Null SHALL NOT be conflated with an empty correction.
- They SHALL NOT be written by any connector, sync or extraction. Only a human
  correction sets them.
- Writing them SHALL NOT modify the linked `Vendor` row, which is a **global**
  catalog shared across organizations.
- `supplier_country_code` SHALL be an ISO 3166-1 alpha-2 code, the same
  vocabulary `Vendor.country_code` uses.

#### Scenario: An override does not touch the vendor

- **WHEN** an invoice's `supplier_country_code` is set
- **THEN** the linked `Vendor.country_code` is unchanged and every other invoice
  referencing that vendor still resolves the catalog value

#### Scenario: No correction means no override

- **WHEN** an invoice has never been corrected
- **THEN** all three override columns are null

### Requirement: Invoice and InvoiceLine record which fields a human verified

`Invoice` and `InvoiceLine` SHALL each carry a `verified_fields` column listing
the field names a human settled, and `Invoice` SHALL additionally carry
`verified_at` and `verified_by`.

- `verified_fields` SHALL default to an empty list, which means "nothing settled"
  — distinct from a null that would be ambiguous.
- A field SHALL be added to the list when a human's verify or correction sets it,
  and SHALL persist across later automated writes.
- `verified_by` SHALL hold the acting user's id; `system` SHALL never appear
  there — an automated write is not a verification.
- The list SHALL be per field, not per row, so an invoice can hold one settled
  field and a dozen unsettled ones.
- These columns record the fact of verification. The values themselves stay in
  their own columns, and their prior values stay in `AuditLog`.

#### Scenario: A correction records the field

- **WHEN** a manager verifies an invoice correcting only its tax
- **THEN** `verified_fields` contains `tax` and no other field

#### Scenario: An unverified row lists nothing

- **WHEN** an invoice has never been verified
- **THEN** its `verified_fields` is an empty list and `verified_at` is null

#### Scenario: Verification is attributed to a user

- **WHEN** an invoice is verified
- **THEN** `verified_by` is the acting user's id, never `system`

## MODIFIED Requirements

### Requirement: InvoiceLine records where it came from

`InvoiceLine` SHALL carry a non-null `origin` of `erp`, `document_ai`,
`entry_fallback`, or `human`, recording which source produced the line.

- `erp` — the ERP supplied the line itself (a bill line on the voucher).
- `document_ai` — our AI extracted the line from the invoice's attached document.
- `entry_fallback` — no document extraction was available, so the line stands in
  for one expense posting on the voucher.
- `human` — a reviewer added the line by hand, typically splitting a stand-in
  line into what was actually bought.
- Precedence between sources SHALL be `human` > `document_ai` > `erp` >
  `entry_fallback`. A person who read the document outranks a model that read it;
  the document is the only source that knows what was actually bought; the ERP's
  own lines are its statement of the same voucher; a posting is the last resort.
- `origin` SHALL be a property of the line and SHALL NOT be inferred from its
  values at read time. A stand-in line and an extracted line can carry identical
  descriptions and amounts, and the difference — whether anyone has read the
  document — is exactly what a reader needs to know.
- An invoice SHALL NOT hold lines of more than one **automated** origin at a
  time. Two automated origins describe the same spend twice and its total would
  be double-counted. `human` lines are the exception: a reviewer splitting a
  stand-in adds `human` lines beside the ones they have not yet replaced, and the
  reconciliation warning — not a storage rule — is what tells them the total no
  longer adds up.
- A `human` line SHALL NOT be refreshed or removed by a sync or a document
  extraction. Neither source has any statement about a line it did not produce.
- Existing rows SHALL be backfilled to `erp`, which is what every line written
  before this change was.

#### Scenario: A line states its source

- **WHEN** a line is read back
- **THEN** it carries an `origin` of `erp`, `document_ai`, `entry_fallback` or
  `human`

#### Scenario: A stand-in and an extracted line are distinguishable

- **WHEN** a stand-in line and an extracted line carry the same description and
  amount
- **THEN** they are still told apart by `origin`

#### Scenario: One automated origin per invoice

- **WHEN** an invoice's lines are listed
- **THEN** every line that is not `human` shares the same `origin`

#### Scenario: A human line outlives a re-sync

- **WHEN** an invoice carrying a `human` line is re-synced
- **THEN** the `human` line is present and unchanged
