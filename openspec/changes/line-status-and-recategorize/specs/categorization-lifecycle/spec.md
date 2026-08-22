## MODIFIED Requirements

### Requirement: Per-line categorization status lifecycle

An `InvoiceLine` SHALL carry a categorization status with the values `uncategorized` (imported, not yet categorized), `ai_failed` (the AI could not categorize it), `ai_categorized` (the AI assigned a category), and `verified` (a human confirmed or corrected the categorization). A line starts `uncategorized`. AI categorization moves it to `ai_categorized` or `ai_failed`. Human verification moves it to `verified` from any prior state.

`ai_failed` SHALL NOT be terminal. Because the AI processes only `uncategorized` lines, a
failure would otherwise be permanent — no re-sync, backfill, or improvement to the
categorizer could ever reach the backlog it had already lost. An explicit, audited request
SHALL be able to return an `ai_failed` line to `uncategorized`, and that SHALL be the only
transition that moves a line backwards through the lifecycle.

#### Scenario: AI categorizes a line

- **WHEN** the AI assigns a category to an `uncategorized` line
- **THEN** the line's status becomes `ai_categorized` and its result fields are populated

#### Scenario: AI fails to categorize

- **WHEN** the AI cannot assign a category to a line
- **THEN** the line's status becomes `ai_failed` and its result fields remain null

#### Scenario: Verified is terminal-by-intent

- **WHEN** a line is `verified`
- **THEN** a subsequent AI re-categorization SHALL NOT overwrite it unless explicitly re-triggered for that line

#### Scenario: A failure can be requeued

- **WHEN** an `ai_failed` line is explicitly requeued
- **THEN** its status returns to `uncategorized` and the next AI run processes it again

#### Scenario: Only an explicit request moves a line backwards

- **WHEN** a sync runs over a company holding `ai_failed` lines without such a request
- **THEN** those lines keep status `ai_failed` and are not reprocessed
