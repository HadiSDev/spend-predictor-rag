# audit-log Specification

## Purpose
TBD - created by archiving change categorization-on-line. Update Purpose after archive.
## Requirements
### Requirement: Append-only audit log

The system SHALL record domain changes in an append-only `AuditLog`. Each entry SHALL capture `entity_type` (e.g. `invoice`, `invoice_line`), `entity_id`, `action` (e.g. `ai_categorize`, `verify`, `edit`), `actor` (the acting user's id, or `system` for automated/AI changes), the `changes` (per-field old→new values), and a timestamp. Audit entries SHALL NOT be updated, ever — history is immutable.

An entry SHALL be deleted only when the entity it describes is itself destroyed,
and only as part of that destruction.

The narrowing is deliberate and has exactly one caller: deleting a company. An
audit row carries no `company_id` and no foreign key — its only tenancy anchor is
the entity it names — so a row left behind after that entity is gone can never
again be attributed to an organization, filtered from an admin view, or answered
for in a data-removal request. It stops being history at that point and becomes
one tenant's field-level values stranded in a table nobody can scope. Nothing
else in the system destroys an entity: extraction supersedes lines and records
the removal, deactivation removes nothing.

#### Scenario: AI categorization is attributed to the system

- **WHEN** the AI pipeline categorizes an invoice line
- **THEN** an `AuditLog` entry is written with `action = ai_categorize`, `actor = system`, and the fields it set

#### Scenario: Human action is attributed to the user

- **WHEN** a user verifies or edits a line's categorization
- **THEN** an `AuditLog` entry is written with the acting user's id as `actor` and the changed fields

#### Scenario: History accumulates

- **WHEN** a line is AI-categorized and later verified by a user
- **THEN** both events remain in the audit log in order, neither overwriting the other

#### Scenario: An entry is never rewritten

- **WHEN** a line that already has audit history is corrected again
- **THEN** a new entry is appended and the existing entries are unchanged

#### Scenario: Superseding a line keeps its history

- **WHEN** an extraction replaces an invoice's lines
- **THEN** the removed lines' audit entries remain, because the invoice they
  belong to still exists

#### Scenario: Destroying the entity takes its entries

- **WHEN** a company is deleted, destroying its invoices and lines
- **THEN** the audit entries describing those invoices and lines are removed with
  them, leaving none that reference an entity that no longer exists

### Requirement: Audit entries are scoped and retrievable

Audit entries SHALL be scoped to the owning organization (via the referenced entity's company) so they are only readable by that tenant, and SHALL be retrievable for a given entity to reconstruct its change history.

#### Scenario: Tenant isolation of history

- **WHEN** a caller reads the audit history for an entity
- **THEN** only entries for entities within the caller's organization are returned

### Requirement: Every newly correctable field joins its audit field set

A field that becomes correctable SHALL be added to the audit field set covering
its entity in the same change that makes it correctable.

A correction is applied in place, over the ERP's or the extractor's own value.
There is no shadow column holding what was there before — the audit row's `old`
value is the only record of it. A correctable field missing from its audit set is
therefore a field whose original value is destroyed by the first correction, with
no error and nothing to notice.

Specifically, this change SHALL add:

- `item_name` to the line value-audit set, beside `description`.
- `document_invoice_number` to the invoice audit set.

Because the document-replacement and line-withdrawal paths both build their
removal audits from the line value-audit set, adding `item_name` there SHALL
propagate to both without further change — and the specs for those paths SHALL
NOT restate the field list.

#### Scenario: A corrected item name is recoverable

- **WHEN** a line's `item_name` is corrected from "Figma seats" to "Figma
  Organization seats"
- **THEN** an audit row records `item_name` with the old value "Figma seats"

#### Scenario: A corrected printed invoice number is recoverable

- **WHEN** an invoice's `document_invoice_number` is corrected
- **THEN** an audit row records the field with the value the extractor had read

#### Scenario: A superseded line's item name is preserved

- **WHEN** an extraction replaces a line that carried an item name
- **THEN** the `superseded_by_extraction` audit row carries that item name

#### Scenario: The audit set is the single list

- **WHEN** the removal-audit paths record a withdrawn or superseded line
- **THEN** the fields they record are exactly the line value-audit set, with no
  separately maintained copy

### Requirement: Corrections to parsed invoice data are fully audited

Every correctable invoice and line field SHALL be covered by the audit trail.
Because corrections are applied in place, over the ERP's or the extractor's own
value, the audit trail is the **only** record of what was originally stated.

- The audited invoice field set SHALL cover `invoice_number`, `invoice_date`,
  `currency`, `total`, `tax`, `vendor_id`, `supplier_name`,
  `supplier_country_code` and `supplier_vat_number`, plus the base/FX fields
  cleared as a consequence.
- The audited line field set SHALL cover `description`, `quantity`, `unit`,
  `unit_price` and `amount`, plus the line's base/FX fields cleared as a
  consequence, in addition to the categorization fields already audited.
- A request that changes nothing SHALL be recorded as `noop`, never as an `edit`
  — the feed must not show a change that did not happen.

#### Scenario: A corrected total is recoverable

- **WHEN** a manager changes an invoice's total from the ERP's figure
- **THEN** an audit entry carries the ERP's figure as `old` and the correction as
  `new`

#### Scenario: A cleared conversion is in the same entry

- **WHEN** a correction to a line's amount clears its base amount
- **THEN** one audit entry carries both the amount change and the cleared base
  fields

#### Scenario: An unchanged submission is a noop

- **WHEN** a correction resubmits the values already stored
- **THEN** the audit action is `noop`

### Requirement: Verification, line creation and line deletion are audit actions

The `invoice` and `invoice_line` entities SHALL support the actions `verify`,
`line_added` and `line_deleted` alongside the existing `ai_categorize`, `edit`
and `noop`.

- `verify` SHALL be recorded on the `invoice` entity when a human accepts the
  parsed header without changing a value; a verification that also corrects SHALL
  be recorded as `edit`.
- `line_added` SHALL be recorded on the `invoice` entity, naming the created
  line, so an invoice's own history shows its line set changing.
- `line_deleted` SHALL be recorded on both the `invoice_line` entity (carrying
  the deleted line's field values and categorization) and the `invoice` entity,
  since the line's own history becomes unreachable through a row that no longer
  exists.

#### Scenario: A header verification is recorded

- **WHEN** a manager verifies an invoice header without corrections
- **THEN** an audit entry with action `verify` and the user's id as actor is
  appended to the invoice's history

#### Scenario: A deleted line's values survive it

- **WHEN** a manager deletes a line carrying a verified category
- **THEN** an audit entry records the line's description, amount and
  categorization

#### Scenario: The invoice's history shows the line change

- **WHEN** a line is added and another deleted
- **THEN** the invoice's audit feed carries a `line_added` and a `line_deleted`
  entry, in order

### Requirement: A hard reset over a verified value is attributed to the system

A `--hard-reset` overwrite of a human-verified field SHALL be audited with actor
`system`, so the human's value remains recoverable exactly as the ERP's is after
a correction.

#### Scenario: The overwrite is recorded

- **WHEN** `--hard-reset` replaces a verified total with the ERP's
- **THEN** an audit entry with actor `system` carries the human's value as `old`
  and the ERP's as `new`

