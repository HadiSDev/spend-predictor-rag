## ADDED Requirements

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
