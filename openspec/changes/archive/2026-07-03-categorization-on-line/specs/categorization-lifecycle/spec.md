## ADDED Requirements

### Requirement: Per-line categorization status lifecycle

An `InvoiceLine` SHALL carry a categorization status with the values `uncategorized` (imported, not yet categorized), `ai_failed` (the AI could not categorize it), `ai_categorized` (the AI assigned a category), and `verified` (a human confirmed or corrected the categorization). A line starts `uncategorized`. AI categorization moves it to `ai_categorized` or `ai_failed`. Human verification moves it to `verified` from any prior state.

#### Scenario: AI categorizes a line

- **WHEN** the AI assigns a category to an `uncategorized` line
- **THEN** the line's status becomes `ai_categorized` and its result fields are populated

#### Scenario: AI fails to categorize

- **WHEN** the AI cannot assign a category to a line
- **THEN** the line's status becomes `ai_failed` and its result fields remain null

#### Scenario: Verified is terminal-by-intent

- **WHEN** a line is `verified`
- **THEN** a subsequent AI re-categorization SHALL NOT overwrite it unless explicitly re-triggered for that line

### Requirement: AI categorization writes the result onto the line

AI categorization SHALL write the result directly onto the `InvoiceLine` — `level_1`, `level_2`, `level_3`, `account_code`, `account_name`, `confidence`, `rationale`, and the resolved `spend_category_id` when it maps to the company's spend tree — and SHALL record an `AuditLog` entry attributed to `system`. There is no separate domain categorization row.

#### Scenario: Result is readable on the line

- **WHEN** a line has been AI-categorized
- **THEN** its category, confidence, and rationale are readable directly from the line

### Requirement: Human verification

The API SHALL let an authorized user (management role) verify an invoice line, optionally correcting its category fields, which sets the line's status to `verified` and records an `AuditLog` entry attributed to that user. Verification of a corrected line SHALL persist the corrected values as the line's categorization.

#### Scenario: Verify accepts the AI result

- **WHEN** a manager verifies an `ai_categorized` line without changes
- **THEN** the line's status becomes `verified` and an audit entry records the verification

#### Scenario: Verify with correction

- **WHEN** a manager verifies a line while changing its category
- **THEN** the corrected values are saved, status becomes `verified`, and the audit entry records the field changes

#### Scenario: Non-manager cannot verify

- **WHEN** a `member` or `viewer` attempts to verify a line
- **THEN** the API responds `403 Forbidden` and the line is unchanged

### Requirement: Invoice status rolls up from its lines

`Invoice.status` SHALL be derived from its lines: `uncategorized` while no line is categorized, an in-progress/`categorized` state once lines are AI-categorized, and `verified` once all lines are `verified`. The rollup SHALL be recomputed when a line's status changes.

#### Scenario: Invoice becomes verified when all lines are

- **WHEN** the last remaining unverified line of an invoice is verified
- **THEN** the invoice's status becomes `verified`

### Requirement: Ground truth lives only in the AI project

Synthetic ground-truth values (`gt_*`) SHALL NOT exist on the domain `InvoiceLine`; they SHALL be stored only in an ai_api-owned store for benchmarking. For real (non-synthetic) data, a `verified` line's values SHALL be treated as the truth for evaluation.

#### Scenario: Domain line has no ground-truth fields

- **WHEN** inspecting the domain `InvoiceLine`
- **THEN** it exposes no `gt_*` fields; ground truth is only in the AI project's store

#### Scenario: Verified data is the truth for real data

- **WHEN** the AI project evaluates accuracy on real data
- **THEN** it treats `verified` lines' categories as the reference truth
