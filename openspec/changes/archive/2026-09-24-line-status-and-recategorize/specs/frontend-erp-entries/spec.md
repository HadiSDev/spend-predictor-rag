## ADDED Requirements

### Requirement: A line's categorization status is a column of its own

The expanded line table and the voucher drawer's Lines tab SHALL show each line's
categorization status as its own labelled column, from the payload's `status`.

The Spend category column SHALL NOT carry this meaning. An empty category renders `—` for
a line nobody has categorized yet, a line the AI failed on, and a line whose company has no
spend tree — three different situations that a reader currently cannot tell apart, and the
middle one is the only one that is a failure.

- The four statuses SHALL be presented with distinct, human-readable labels rather than the
  raw enum values: `uncategorized`, `ai_failed`, `ai_categorized`, `verified`.
- `ai_failed` SHALL be the only status presented as a problem. `uncategorized` is a backlog
  and `verified` is the goal, so styling either as an error would make the signal useless.
- The status SHALL come from the payload's `status` field and SHALL NOT be inferred from
  whether the category levels are populated — an `ai_failed` line and an `uncategorized`
  line both have null levels.
- The status SHALL be conveyed by its label, not by colour alone.

#### Scenario: A failed line is distinguishable from an uncategorized one

- **WHEN** one line has `status = ai_failed` and another has `status = uncategorized`
- **THEN** the two rows show different status labels, though both show `—` for category

#### Scenario: The failure reads as a failure

- **WHEN** a line with `status = ai_failed` is rendered
- **THEN** its status is presented as a problem state, distinct in styling from the other
  three

#### Scenario: A backlog line is not an error

- **WHEN** a line with `status = uncategorized` is rendered
- **THEN** nothing on the row is presented as a failure

#### Scenario: The status survives a missing category

- **WHEN** a line with `status = ai_categorized` has its `spend_category_id` cleared and
  its levels retained
- **THEN** the status column still reads as AI-categorized

#### Scenario: The label carries the meaning without colour

- **WHEN** the status is rendered
- **THEN** its text alone identifies which of the four states the line is in

### Requirement: A stale category is shown beside the status, not as one

A line whose `category_stale` is true SHALL be marked in the status column, distinctly from
its `status` value and without replacing it.

`category_stale` is computed, not stored, and is orthogonal to the lifecycle: a line can be
`verified` and stale at once, meaning a human categorized it and the taxonomy later moved.
Presenting it as a fifth status would erase whichever real status the line holds.

#### Scenario: A stale verified line shows both facts

- **WHEN** a line has `status = verified` and `category_stale = true`
- **THEN** the row shows that it is verified **and** that its category needs review

#### Scenario: Stale is not a status

- **WHEN** a stale line is rendered
- **THEN** its `status` value is still shown, not replaced by the stale marker
