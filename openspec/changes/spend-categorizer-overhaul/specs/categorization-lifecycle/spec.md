## MODIFIED Requirements

### Requirement: Per-line categorization status lifecycle

An `InvoiceLine` SHALL carry a categorization status with the values `uncategorized` (imported, not yet categorized), `ai_failed` (the AI could not categorize it), `ai_categorized` (the AI assigned a category), and `verified` (a human confirmed or corrected the categorization). A line starts `uncategorized`. AI categorization moves it to `ai_categorized` or `ai_failed`. Human verification moves it to `verified` from any prior state.

`ai_failed` SHALL mean a **fault**, not a judgement. It is reached when the model answers with something that is not one of the candidates offered, or when no candidate set could be built at all. It SHALL NOT be reached because the model found the line hard: the model always returns a category, and doubt is recorded as a low confidence on an `ai_categorized` line. Reporting an honest "nothing here fits well" as a failure told a reviewer the software was broken when the taxonomy was incomplete, and pointed them at no remedy.

A model that could not be reached, or whose reply could not be parsed, SHALL leave the line `uncategorized` rather than `ai_failed`, so the next run retries it without an explicit requeue.

#### Scenario: AI categorizes a line

- **WHEN** the AI assigns a category to an `uncategorized` line
- **THEN** the line's status becomes `ai_categorized` and its result fields are populated

#### Scenario: A hard line is categorized with low confidence, not failed

- **WHEN** the AI finds no candidate that fits the line well
- **THEN** it returns its best candidate, the line becomes `ai_categorized`, and the confidence records the doubt

#### Scenario: AI fails to categorize

- **WHEN** the model answers with a candidate number that was never offered
- **THEN** the line's status becomes `ai_failed` and its result fields remain null

#### Scenario: An outage is not a failure

- **WHEN** the model cannot be reached while a line is being categorized
- **THEN** the line stays `uncategorized` and no status change is recorded

#### Scenario: Verified is terminal-by-intent

- **WHEN** a line is `verified`
- **THEN** a subsequent AI re-categorization SHALL NOT overwrite it unless explicitly re-triggered for that line

### Requirement: AI categorization writes the result onto the line

AI categorization SHALL write the result directly onto the `InvoiceLine` — `level_1`, `level_2`, `level_3`, `level_4`, `account_code`, `account_name`, `confidence`, `rationale`, and the resolved `spend_category_id` when it maps to a node of the company's **assigned** spend tree — and SHALL record an `AuditLog` entry attributed to `system`. There is no separate domain categorization row.

The candidate set the AI chooses from SHALL be the nodes of the company's assigned tree. When the company's tree is four levels deep, the result MAY name a depth-4 node and `level_4` SHALL then be set; on a three-level tree `level_4` SHALL remain null.

`confidence` SHALL be a number between 0 and 1 and SHALL be populated on every `ai_categorized` line. It is now load-bearing rather than informational: it is what a reviewer sorts by, what the review filter selects on, and what the tree-gap suggester reads. A categorization written without one would be indistinguishable from a certain answer.

#### Scenario: Result is readable on the line

- **WHEN** a line has been AI-categorized
- **THEN** its category, confidence, and rationale are readable directly from the line

#### Scenario: Every AI result carries a confidence

- **WHEN** any line reaches `ai_categorized`
- **THEN** its `confidence` is set and lies between 0 and 1

#### Scenario: The candidate set is the assigned tree

- **WHEN** two companies in one organization are assigned different trees
- **THEN** each company's lines are categorized only against its own tree's nodes

#### Scenario: A four-level match records its leaf

- **WHEN** the AI matches a depth-4 node
- **THEN** the line's `level_4` holds that node's name and `spend_category_id` names that node

## ADDED Requirements

### Requirement: A low-confidence categorization SHALL be reviewable as a class

Because the AI now always returns a category, low confidence SHALL be the signal that a human should look. The platform SHALL make low-confidence AI results selectable as a group, so a reviewer can work the doubtful decisions without reading every line.

The threshold SHALL be a platform setting rather than a value written into a line, for the same reason `category_stale` is computed and not stored: it is a judgement about how much doubt is tolerable, it will be tuned, and every historical line must move when it is.

#### Scenario: Doubtful lines can be listed

- **WHEN** a reviewer asks for lines needing review
- **THEN** the `ai_categorized` lines whose confidence falls below the threshold are returned

#### Scenario: A verified line leaves the review set

- **WHEN** a human verifies a low-confidence line
- **THEN** it no longer appears among the lines needing review, whatever its confidence was

#### Scenario: Changing the threshold moves history

- **WHEN** the threshold is raised
- **THEN** previously-categorized lines below the new threshold appear in the review set without being rewritten
