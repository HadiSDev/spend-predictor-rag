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

