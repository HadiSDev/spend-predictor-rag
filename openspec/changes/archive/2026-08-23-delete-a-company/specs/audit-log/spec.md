## MODIFIED Requirements

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
