## Why

Categorization was moved into a separate ai_api-owned `LineCategorization` store, leaving the domain `InvoiceLine` to hold only an accepted `spend_category_id`. That split adds a join and a second write for every line, and it has no home for the human-in-the-loop workflow the product needs: an AI result that a person can review and mark **verified**. We want the line to be the single record of its own categorization, an explicit lifecycle (uncategorized → AI result → human-verified), and a change history so we can see who changed what and when. Synthetic ground truth remains an AI-project concern — and once a line is human-verified, that verified value *is* our truth.

## What Changes

- **Remove `LineCategorization`** (ai_api). The categorization result lives directly on `InvoiceLine`: `level_1`, `level_2`, `level_3`, `account_code`, `account_name`, `confidence`, `rationale` (alongside the existing accepted `spend_category_id`).
- **Line categorization status** on `InvoiceLine.status`: `uncategorized` → `ai_failed` | `ai_categorized` → `verified` (a human has confirmed/corrected the categorization).
- **Invoice status is a rollup** of its lines (e.g. `uncategorized` until any line is categorized, `verified` once all lines are verified).
- **Generic `AuditLog`** (domain): every categorization change is recorded — `entity_type` (`invoice`/`invoice_line`), `entity_id`, `action` (`ai_categorize`/`verify`/`edit`), `actor` (a user id, or `system` for the AI), the per-field `changes`, and a timestamp. AI categorization writes an audit row as `system`; human verification/edits write one as the acting user.
- **Human verification endpoint** (web_api): a manager can verify a line (optionally correcting its category), transitioning it to `verified` and writing an audit entry.
- **Ground truth stays in the AI project**: a small ai_api-owned store keeps synthetic `gt_*` for benchmarking; the domain model carries no `gt_*`. For real data, verified lines are treated as truth.

## Capabilities

### New Capabilities
- `audit-log`: the generic, append-only change history (entity, action, actor, field-level diffs) that categorization and verification write to.
- `categorization-lifecycle`: the per-line status lifecycle (`uncategorized`/`ai_failed`/`ai_categorized`/`verified`), what AI categorization writes onto the line, human verification, the invoice-status rollup, and the rule that ground truth lives only in the AI project.

### Modified Capabilities
- `domain-model`: `InvoiceLine` carries the categorization result + the new status vocabulary (replacing `pending`/`categorizing`/`completed`/`failed` for lines); `Invoice.status` becomes a rollup; new `AuditLog` entity; `gt_*` and the `LineCategorization` store are removed from the domain.

## Impact

- **Schema/ORM**: add categorization + evidence columns to `invoice_lines`; new line status values; new `audit_log` table; drop `line_categorizations`; add a small ai_api `line_ground_truth` table (synthetic `gt_*`). One Alembic migration.
- **ai_api**: the sync runner writes categorization results onto `InvoiceLine` (status `ai_categorized`/`ai_failed`), records an `AuditLog` entry as `system`, and writes synthetic `gt_*` to `line_ground_truth`; remove `ai_api/persistence/categorization.py` (`LineCategorization`).
- **web_api**: `AuditLog` model; a verify endpoint (`POST /api/v1/invoice-lines/{id}/verify`, management role) that sets `verified` + audits; read schemas expose the line's categorization + status.
- **Tests**: rewrite `test_sync_runner` expectations (result on line, no `LineCategorization`), plus new audit + verification tests and invoice-rollup assertions.
