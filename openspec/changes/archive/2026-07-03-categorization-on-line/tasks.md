## 1. Schema & migration

- [x] 1.1 Add categorization result columns to `InvoiceLine`: `level_1`, `level_2`, `level_3`, `account_code`, `account_name`, `confidence` (Numeric(4,3)), `rationale` (keep `spend_category_id`, `status`, `error_message`)
- [x] 1.2 Update `InvoiceLine.status` usage to the vocabulary `uncategorized|ai_failed|ai_categorized|verified` (default `uncategorized`)
- [x] 1.3 Add `AuditLog` model (`entity_type`, `entity_id`, `action`, `actor`, `changes` JSON, `created_at`) in `web_api/db/models/`, registered in the models `__init__`
- [x] 1.4 Add ai_api-owned `line_ground_truth` store (`invoice_line_id` unique FK, `gt_level_1..3`, `gt_account_code`) in `ai_api/persistence/`
- [x] 1.5 Remove `ai_api/persistence/categorization.py` (`LineCategorization`) and its export
- [x] 1.6 Alembic migration: add invoice_line columns, create `audit_log` + `line_ground_truth`, drop `line_categorizations`; apply to dev DB (reset dev data if no real data exists)

## 2. Categorization write path (ai_api)

- [x] 2.1 Runner writes the categorization result directly onto `InvoiceLine` (level_*/account/confidence/rationale + resolved `spend_category_id`), setting status `ai_categorized` or `ai_failed`
- [x] 2.2 Runner writes synthetic `gt_*` to `line_ground_truth` (not the line)
- [x] 2.3 Runner appends an `AuditLog` row per categorized line (`actor='system'`, `action='ai_categorize'`, field diffs) in the same transaction
- [x] 2.4 Runner does not overwrite a `verified` line unless explicitly re-triggered
- [x] 2.5 Recompute `Invoice.status` rollup after line updates (shared helper)

## 3. Verification + audit (web_api)

- [x] 3.1 Shared helper to build field diffs and append an `AuditLog` entry (used by AI and human paths)
- [x] 3.2 `POST /api/v1/invoice-lines/{id}/verify` — `require_management`, tenant-scoped (404 for foreign line); optional corrected category fields in the body; sets status `verified`, persists corrections, appends an audit entry (`actor=user`, `action=verify`/`edit`)
- [x] 3.3 Recompute the invoice rollup when a line becomes `verified`
- [x] 3.4 Extend invoice-line read schema to expose level_*/account/confidence/rationale/status; add an audit-history read (`GET /api/v1/invoice-lines/{id}/audit`, tenant-scoped)

## 4. Tests

- [x] 4.1 Rewrite `test_sync_runner`: result + status on the line (no `LineCategorization`); `ai_categorized` vs `ai_failed`; `gt_*` in `line_ground_truth`; invoice rollup
- [x] 4.2 Audit: AI categorization writes a `system` audit row; verify writes a user row; history accumulates and is tenant-scoped
- [x] 4.3 Verify endpoint: manager verifies (accept + correct) → `verified` + audit; member/viewer → `403`; foreign line → `404`
- [x] 4.4 Verified line not overwritten by a re-run
- [x] 4.5 Invoice rollup: becomes `verified` when all lines verified
- [x] 4.6 Run `uv run pytest` — full suite green

## 5. Docs

- [x] 5.1 Update `CLAUDE.md` (categorization on the line, status lifecycle, AuditLog, verify endpoint, ground truth in ai_api)
