## ADDED Requirements

### Requirement: AI categorization results are persisted in an ai_api-owned store

The AI pipeline SHALL persist per-line categorization results in an `ai_api`-owned entity (`LineCategorization`) that is separate from the `web_api` domain models, so that AI prediction data and evidence never live as columns on domain tables.

- The store SHALL hold, per categorized line: the predicted category snapshot
  (`level_1`, `level_2`, `level_3`, `account_code`, `account_name`), the match
  `confidence` and `rationale`, and the synthetic ground truth (`gt_level_1`,
  `gt_level_2`, `gt_level_3`, `gt_account_code`).
- The store SHALL key each result by `invoice_line_id`, with at most one result
  row per invoice line.
- The `web_api` domain package SHALL NOT import, reference, or relate to this
  entity; the dependency direction stays one-way (`ai_api → web_api`).

#### Scenario: Categorizing a line records a result in the AI store

- **WHEN** the sync pipeline categorizes an invoice line
- **THEN** a `LineCategorization` row keyed by that `invoice_line_id` is written
  with the predicted level snapshot, confidence, rationale, and ground truth, and
  no AI prediction columns are written on the `InvoiceLine`

#### Scenario: Re-categorizing the same line does not duplicate results

- **WHEN** the sync pipeline categorizes a line that already has a result
- **THEN** its existing `LineCategorization` row is updated in place (still one
  row per `invoice_line_id`)

### Requirement: The AI store references domain rows by id without ORM coupling

`LineCategorization` SHALL reference domain rows (`invoice_lines`, `spend_categories`) by id-valued foreign-key columns only, with no ORM relationship reaching into domain model classes and no back-population on domain models.

- Deleting an `InvoiceLine` SHALL cascade-delete its `LineCategorization` row.
- `spend_category_id` on the store SHALL be nullable (populated only when the
  match resolves to a real `SpendCategory`).

#### Scenario: Deleting a line removes its categorization result

- **WHEN** an `InvoiceLine` is deleted
- **THEN** its `LineCategorization` row is removed by the database cascade

### Requirement: The spend rollup reads the AI store

The sync summary's spend-by-category rollup SHALL derive category labels from the AI store's predicted levels joined to the line amounts, not from columns on `InvoiceLine`.

#### Scenario: Rollup aggregates by the predicted level from the AI store

- **WHEN** the sync pipeline builds its summary after categorizing lines
- **THEN** `spend_by_level_2` groups line amounts by the predicted `level_2` stored
  in `LineCategorization`
