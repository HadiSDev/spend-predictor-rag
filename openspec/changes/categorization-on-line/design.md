## Context

A prior refactor moved categorization off the domain `InvoiceLine` into an ai_api-owned `LineCategorization` (prediction + evidence + synthetic `gt_*`), leaving the line with only an accepted `spend_category_id`. That boundary added a join and a second write per line and left no place for a human review/verify workflow. We are folding the categorization result back onto the line, adding an explicit lifecycle and a generic audit trail, and keeping only synthetic ground truth in the AI project. This partially reverses the ai_api/web_api split for categorization *values* (confidence/rationale now live on the domain line) — an accepted trade for simplicity and a first-class verify workflow.

## Goals / Non-Goals

**Goals:**
- One record per line: `InvoiceLine` holds levels, `account_code`/`name`, `confidence`, `rationale`, `spend_category_id`, and a categorization `status`.
- Lifecycle: `uncategorized` → `ai_failed` | `ai_categorized` → `verified`; `Invoice.status` rolls up.
- Generic append-only `AuditLog` (entity, action, actor, field diffs); AI writes as `system`, humans as themselves.
- Human verify endpoint (management role), optionally correcting the category.
- Ground truth stays in an ai_api store; verified lines are truth for real data.

**Non-Goals:**
- No re-categorization queue/scheduler (re-categorize remains a manual trigger, out of scope here).
- No per-field-level UI diffing beyond storing the diffs.
- No audit for entities other than invoice / invoice_line in this change.

## Decisions

### Result on the line; drop `LineCategorization`
The line carries `level_1..3`, `account_code`, `account_name`, `confidence`, `rationale` plus the existing `spend_category_id`. The AI writes these directly. This removes a join and a table. Alternative (keep the split) was rejected per the product need for a single, verifiable line record.

### Status vocabulary is line-first, invoice rolls up
`InvoiceLine.status ∈ {uncategorized, ai_failed, ai_categorized, verified}`. `Invoice.status` is derived from its lines (uncategorized → categorized/in-progress → verified) and recomputed whenever a line's status changes, in the same transaction. Keeping the rollup derived avoids the invoice and its lines drifting out of sync.

### Generic `AuditLog`, not per-entity tables
One `audit_log` table: `entity_type`, `entity_id`, `action`, `actor`, `changes` (JSON list of `{field, old, new}`), `created_at`. One place to query history for both invoices and lines; `actor` is a user id or the sentinel `system`. Chosen over separate `InvoiceLineAudit`/`InvoiceAudit` tables (the user's initial naming) to avoid duplicated schema and split queries. Append-only by convention (no update/delete paths).

### Ground truth is ai_api-only (`line_ground_truth`)
A small ai_api-owned table keyed by `invoice_line_id` holds `gt_level_1..3`, `gt_account_code` for synthetic benchmarking; the domain line has no `gt_*`. For real data the AI project reads `verified` lines as truth. This preserves the one-way ai_api→web_api dependency for the *benchmarking* concern while letting the *result* live on the domain line.

### Writes and attribution
The sync runner (ai_api) writes the result + status onto the line and appends an `AuditLog` row with `actor='system'`, `action='ai_categorize'`, in the same transaction as the line update. The verify endpoint (web_api) sets `verified` (+ any corrected fields) and appends an `AuditLog` row with the caller's user id and `action='verify'` (or `edit`). A tiny shared helper builds the field-diff so both paths record consistent `changes`.

### Verify endpoint placement
`POST /api/v1/invoice-lines/{id}/verify` gated by `require_management`, tenant-scoped (404 for foreign lines), body optionally carrying corrected category fields. Reuses the existing management authorization + tenant-scope dependencies.

## Risks / Trade-offs

- **AI fields on the domain model** → accepted; documented as an intentional reversal. `web_api` still never imports ai_api; only the *values* moved.
- **Verified lines overwritten by a later AI run** → the runner skips lines whose status is `verified` unless explicitly re-triggered; covered by a test.
- **Rollup drift** → recompute invoice status in the same transaction as any line status change; assert in tests.
- **Big test churn** → `test_sync_runner` and any LineCategorization-based tests are rewritten; migration must move existing `line_categorizations` data onto lines and into `line_ground_truth` (or, if only synthetic/dev data exists, a create-all reset is acceptable — confirm before dropping).
- **Audit volume** → append-only text/JSON; fine at current scale, revisit retention later.

## Migration Plan

1. Add columns to `invoice_lines` (`level_1..3`, `account_code`, `account_name`, `confidence`, `rationale`); widen `status` values. Add `audit_log` table. Add ai_api `line_ground_truth` table. Drop `line_categorizations`.
2. Data move (if non-trivial data exists): copy prediction/evidence from `line_categorizations` onto lines; copy `gt_*` into `line_ground_truth`. Otherwise reset dev DB.
3. ai_api: runner writes result+status onto the line, `line_ground_truth` for `gt_*`, and an `AuditLog` row; delete `ai_api/persistence/categorization.py`.
4. web_api: `AuditLog` model + verify endpoint + read-schema fields; invoice-status rollup helper.
5. Rewrite/extend tests; run `uv run pytest`.
Rollback: revert the migration (re-create `line_categorizations`) and the code; additive audit/ground-truth tables can be dropped.

## Open Questions

- Exact intermediate `Invoice.status` label once lines are AI-categorized but not all verified (`categorized` vs `ai_categorized` vs `partially_verified`) — default `categorized`; confirm during apply.
- Whether existing `line_categorizations` rows need real data migration or a dev reset suffices (depends on whether any non-synthetic data exists yet).
