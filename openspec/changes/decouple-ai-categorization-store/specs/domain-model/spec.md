## ADDED Requirements

### Requirement: InvoiceLine stores the domain category assignment, not AI output

`InvoiceLine` SHALL store only the accepted domain-level category assignment and its own raw/lifecycle fields, and SHALL NOT store AI-produced categorization output or an ERP line identifier.

- `InvoiceLine` SHALL have a nullable `spend_category_id` (FK → `spend_categories`)
  — the accepted line→category assignment, a domain fact.
- `InvoiceLine` SHALL NOT store the AI prediction snapshot (`level_1`, `level_2`,
  `level_3`, `account_code`, `account_name`), the match `confidence`/`rationale`,
  or the synthetic ground truth (`gt_level_1`, `gt_level_2`, `gt_level_3`,
  `gt_account_code`); those live in the `ai_api`-owned categorization store.
- `InvoiceLine` SHALL NOT store a `line_erp_id`; an invoice-scan line carries no
  ERP line identity, consistent with `Invoice` storing no `erp_id`.
- `InvoiceLine` SHALL retain its raw fields (`description`, `quantity`,
  `unit_price`, `amount`, `native_account_code`) and its `status`.

#### Scenario: A categorized line carries only the assignment on the domain model

- **WHEN** a line has been categorized by the AI pipeline
- **THEN** the `InvoiceLine` row exposes `spend_category_id` (set only when the
  match resolves to a real category) and exposes no predicted levels, account
  snapshot, confidence, rationale, or ground-truth columns

#### Scenario: Invoice-scan line has no ERP line id

- **WHEN** an invoice scan with line items is persisted
- **THEN** each `InvoiceLine` stores its raw fields and status but no
  `line_erp_id`

### Requirement: ErpEntry stores no categorization fields

`ErpEntry` SHALL NOT store any categorization output or ground truth. Entries are raw financial context and are never categorized, so the table SHALL carry no `level_1/2/3`, `account_code`, `account_name`, `confidence`, `rationale`, or `gt_*` columns.

- The native account is referenced via `erp_account_id`; it SHALL NOT be
  duplicated as categorization `account_code`/`account_name` on the entry.
- No AI store is introduced for entries (unlike invoice lines), because entries
  are never categorized.

#### Scenario: Persisted entry carries no categorization columns

- **WHEN** the sync pipeline persists `ErpEntry` rows
- **THEN** each entry exposes its raw financial fields, `erp_account_id`, and
  `status`, and the table has no categorization or ground-truth columns
