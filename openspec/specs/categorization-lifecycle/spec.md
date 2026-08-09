# categorization-lifecycle Specification

## Purpose
TBD - created by archiving change categorization-on-line. Update Purpose after archive.
## Requirements
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

### Requirement: Every line is categorized, whatever produced it

The categorizer SHALL treat a line's `origin` as irrelevant to whether it is
categorized. A `document_ai` line, an `erp` line and an `entry_fallback` line
SHALL all move through `uncategorized → ai_categorized | ai_failed → verified`
identically.

- A stand-in line SHALL NOT be held back from categorization pending a document
  that may never arrive. Most vouchers have no scan, and withholding them would
  leave the majority of spend uncategorized.
- Categorization SHALL be the same operation on all three, so a change to the
  categorizer cannot behave differently depending on where a line came from.
- The reports SHALL make no distinction between origins when aggregating spend
  by category. A stand-in line's spend is real spend.

#### Scenario: A stand-in line is categorized

- **WHEN** the categorizer runs over an invoice whose only lines are
  `entry_fallback`
- **THEN** those lines are categorized and become `ai_categorized`

#### Scenario: Origin does not change the outcome

- **WHEN** a stand-in line and an extracted line carry the same description
- **THEN** the categorizer produces the same result for both

#### Scenario: Reports do not discriminate by origin

- **WHEN** `spend-by-category` is requested over a period containing both
  stand-in and extracted lines
- **THEN** both contribute to their categories' totals

### Requirement: Replacing a line by extraction is an audited event

Removing a line so that document extraction can replace it SHALL append an
`AuditLog` row for that line, with `actor = 'system'`, an action naming the
replacement, and the removed line's values in `changes`.

- The audit SHALL record the removed line's categorization result and status, so
  a category a human had verified is recoverable from the record.
- The replacement SHALL be recorded even when the removed line was never
  categorized, so the invoice's history is complete rather than selective.
- Verification of a line is a judgement made **on this platform**, and this
  change does not yet give a human a way to protect a line from replacement.
  Extraction therefore wins: the document is the better evidence, and the
  superseded verification is preserved in the audit log for the human to
  reapply. Any future affordance for locking a line SHALL be built on this
  record.

#### Scenario: A replaced line leaves a record

- **WHEN** an extraction replaces two stand-in lines
- **THEN** two audit rows are appended, each naming the removed line and its
  values, with `actor = 'system'`

#### Scenario: A verified category is recoverable

- **WHEN** a verified line is replaced by extraction
- **THEN** its audit row carries the verified category and status

#### Scenario: An uncategorized removal is recorded too

- **WHEN** an uncategorized stand-in line is replaced
- **THEN** an audit row is still appended for it

### Requirement: The invoice's rollup follows its current lines

`Invoice.status` SHALL be recomputed in the same transaction that replaces an
invoice's lines, from the lines the invoice ends up with.

- An invoice whose verified stand-in lines are replaced by fresh
  `uncategorized` lines SHALL return to `uncategorized`. Leaving it `verified`
  would assert a human judgement over lines no human has seen.
- The rollup SHALL be the existing one; no separate path is introduced for
  replacement.

#### Scenario: Replacement resets a verified invoice

- **WHEN** an invoice reading `verified` has its lines replaced by extraction
- **THEN** it reads `uncategorized` in the same transaction

#### Scenario: The rollup is recomputed once

- **WHEN** the lines of an invoice are replaced
- **THEN** its status is recomputed from the resulting lines, in that
  transaction

