## ADDED Requirements

### Requirement: InvoiceLine carries its categorization result and status

The `InvoiceLine` domain entity SHALL hold its categorization result directly: `level_1`, `level_2`, `level_3`, `account_code`, `account_name`, `confidence`, `rationale`, plus the accepted `spend_category_id` (FK to the company's spend tree, nullable until resolved). Its `status` SHALL use the categorization vocabulary `uncategorized` | `ai_failed` | `ai_categorized` | `verified`. The line SHALL NOT carry synthetic ground-truth (`gt_*`) fields, and there SHALL be no separate domain `LineCategorization` table.

#### Scenario: Result fields on the line

- **WHEN** a line is categorized
- **THEN** its `level_*`, `account_code`, `account_name`, `confidence`, and `rationale` are set on the line and its status reflects `ai_categorized` or `verified`

#### Scenario: No ground truth on the domain line

- **WHEN** inspecting `invoice_lines`
- **THEN** there are no `gt_*` columns

### Requirement: Invoice status is a categorization rollup

`Invoice.status` SHALL reflect the aggregate categorization state of its lines rather than an independent value: `uncategorized` when no line is categorized, a categorized/in-progress state once lines are AI-categorized, and `verified` when every line is `verified`.

#### Scenario: Rollup reflects line states

- **WHEN** all of an invoice's lines are `verified`
- **THEN** the invoice's status is `verified`

### Requirement: AuditLog entity

The domain SHALL include an `AuditLog` entity recording changes over time: `id`, `entity_type` (`invoice` | `invoice_line`), `entity_id`, `action`, `actor` (user id or `system`), `changes` (JSON of per-field old→new values), and `created_at`. It is append-only and scoped to the owning organization through the referenced entity.

#### Scenario: Audit row shape

- **WHEN** a categorization or verification occurs
- **THEN** an `AuditLog` row captures the entity, action, actor, and field changes with a timestamp
