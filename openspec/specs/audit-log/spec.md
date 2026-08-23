# audit-log Specification

## Purpose
TBD - created by archiving change categorization-on-line. Update Purpose after archive.
## Requirements
### Requirement: Append-only audit log

The system SHALL record domain changes in an append-only `AuditLog`. Each entry SHALL capture `entity_type` (e.g. `invoice`, `invoice_line`), `entity_id`, `action` (e.g. `ai_categorize`, `verify`, `edit`), `actor` (the acting user's id, or `system` for automated/AI changes), the `changes` (per-field old→new values), and a timestamp. Audit entries SHALL NOT be updated or deleted in the normal flow — history is immutable.

#### Scenario: AI categorization is attributed to the system

- **WHEN** the AI pipeline categorizes an invoice line
- **THEN** an `AuditLog` entry is written with `action = ai_categorize`, `actor = system`, and the fields it set

#### Scenario: Human action is attributed to the user

- **WHEN** a user verifies or edits a line's categorization
- **THEN** an `AuditLog` entry is written with the acting user's id as `actor` and the changed fields

#### Scenario: History accumulates

- **WHEN** a line is AI-categorized and later verified by a user
- **THEN** both events remain in the audit log in order, neither overwriting the other

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
