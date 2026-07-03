## Why

AI-produced categorization output (predicted category, the level snapshot,
confidence, rationale, and synthetic ground truth) currently lives as columns on
the `web_api` domain model `InvoiceLine`. That couples the business domain to the
AI pipeline's working data and inverts the intended boundary: `ai_api` depends on
`web_api`, never the reverse, yet the domain table now carries fields only the AI
workflow writes and reads. The AI results belong to the AI project, which should
own its own persistence.

## What Changes

- **BREAKING**: Remove AI-produced columns from `InvoiceLine`:
  `level_1`, `level_2`, `level_3`, `account_code`, `account_name`, `confidence`,
  `rationale`, `gt_level_1`, `gt_level_2`, `gt_level_3`, `gt_account_code`.
- **BREAKING**: Remove `line_erp_id` from `InvoiceLine` (an internal invoice
  scan line carries no ERP line identity, mirroring `Invoice` dropping `erp_id`).
- `InvoiceLine` keeps `spend_category_id` — the accepted line→category assignment
  is a domain fact and remains on the domain model.
- Introduce an `ai_api`-owned categorization-result entity, keyed by
  `invoice_line_id` **by id** (no ORM relationship reaching into the domain), that
  holds the AI prediction and evidence (predicted category / level snapshot,
  confidence, rationale) and the synthetic ground truth. This preserves the
  one-way `ai_api → web_api` dependency.
- Rewire the sync runner's categorizer to write results to the AI-owned store and
  set only `InvoiceLine.spend_category_id` on the domain line; rework
  `_build_summary` so the spend rollup no longer reads removed columns.
- **BREAKING**: `GET /api/v1/invoices/{id}` line payloads no longer expose the
  removed categorization columns; they expose `spend_category_id`.
- **BREAKING**: Remove the same vestigial categorization/ground-truth columns
  from `ErpEntry` (`level_1/2/3`, `account_code`, `account_name`, `confidence`,
  `rationale`, `gt_level_1/2/3`, `gt_account_code`). Entries are never categorized,
  so these were always NULL; no AI store is introduced for entries. `ErpEntryRead`
  drops `account_code`/`account_name` accordingly.

## Capabilities

### New Capabilities
- `ai-categorization-store`: `ai_api`-owned persistence for line categorization
  results (prediction, confidence, rationale, ground truth), decoupled from the
  domain schema and referencing domain rows by id only.

### Modified Capabilities
- `domain-model`: `InvoiceLine` no longer stores AI categorization output or an
  ERP line id; it retains `spend_category_id` as the domain-level assignment.
  `ErpEntry` no longer carries categorization/ground-truth columns either. AI
  categorization output SHALL NOT be stored on domain models.
- `web-api-invoice-review`: invoice-line read payloads drop the removed
  categorization columns and surface `spend_category_id` instead.

## Impact

- **Domain models**: `src/web_api/db/models/invoice_line.py` (column removals),
  new Alembic migration to drop the columns.
- **AI persistence**: new `ai_api`-owned model module + its persistence wiring
  (location + migration ownership decided in design).
- **Sync pipeline**: `src/ai_api/sync/runner.py` (`_categorize_pending`,
  `_build_summary`), `src/ai_api/sync/categorizer.py` (result shape unchanged, but
  its output is persisted to the AI store).
- **API contract**: `src/web_api/schemas.py` `InvoiceLineRead`.
- **Tests**: `tests/test_sync_runner.py`, `tests/web_api/` fixtures/assertions.
- **Boundary**: reinforces `web_api` ↛ `ai_api`; AI store references domain ids
  without FKs into `ai_api`.
