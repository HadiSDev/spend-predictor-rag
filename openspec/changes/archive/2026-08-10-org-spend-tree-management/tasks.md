## 1. Domain model and schema

- [x] 1.1 Add `SpendTree` model (`src/web_api/db/models/spend_tree.py`): `organization_id`, `name`, `max_depth`, `source`, `template_version`, `archived_at`, `created_at`; export from `db/models/__init__.py` and add `Organization.spend_trees`
- [x] 1.2 Reparent `SpendCategory`: drop `company_id`, add `spend_tree_id`, `parent_id`, `depth`, `name`, `code`, `sort_order`; add `SpendTree.categories`; remove `Company.spend_categories`
- [x] 1.3 Add `Company.spend_tree_id` + `Company.spend_tree` relationship
- [x] 1.4 Add `InvoiceLine.level_4`
- [x] 1.5 Add unique constraints: `(spend_tree_id, parent_id, name)` and `(spend_tree_id, code)` where code is not null
- [x] 1.6 Write the Alembic revision on top of `0001_baseline_schema`: create tables/columns, migrate existing `spend_categories` rows onto per-company `custom` trees (back-filling `parent_id`/`depth`/`name` from the level path), assign companies, then drop `company_id`; write a lossy but working `downgrade` with its limits stated in the docstring
- [x] 1.7 Update `tests/test_spend_category.py` for the new shape and add model tests for tree/node relationships and the constraints
- [x] 1.8 Verify `uv run pytest tests/web_api/test_migrations.py` passes from base against PostgreSQL

## 2. Spend tree service and default template

- [x] 2.1 Create `src/web_api/spend_trees/template.py`: `TEMPLATE_VERSION` and the 3-level default definition (`Direct`/`Indirect` at level 1), carrying the node data currently in `ai_api/sync/categorizer.py::_META` including its keyword sets
- [x] 2.2 Create `src/web_api/spend_trees/service.py` as the only writer of `SpendCategory`: `create_tree`, `clone_tree`, `add_node`, `rename_node`, `move_node`, `delete_node`, `archive_tree`
- [x] 2.3 Implement `_rewrite_paths()` — maintain `level_1..level_4` from `parent_id`/`name` on every mutation, rewriting descendants in the same transaction
- [x] 2.4 Implement depth enforcement against `SpendTree.max_depth` (reject over-deep node writes; reject lowering `max_depth` while deeper nodes exist)
- [x] 2.5 Implement `ensure_default_tree(session, organization_id)` — return the org's `default_template` tree, creating and seeding it from the template if absent; idempotent per organization
- [x] 2.6 Implement node deletion rules: refuse when children exist; when invoice lines reference the node, clear their `spend_category_id` and leave their levels
- [x] 2.7 Tests: path materialization after rename/move, depth rejection, idempotent default seeding, sibling-uniqueness conflict, delete rules

## 3. CSV import

- [x] 3.1 Create `src/web_api/spend_trees/importer.py`: parse `level_1..level_4`, `description`, optional `code`
- [x] 3.2 Validate the whole file before any write — depth vs `max_depth`, path gaps, duplicate sibling paths, duplicate codes — returning per-row errors with file line numbers
- [x] 3.3 Implement `mode=merge` (add/update) and `mode=replace` (also remove), applied atomically
- [x] 3.4 Implement the replace guard: 409 with the affected invoice-line count unless `confirm=true`; on confirm, clear those lines' pointers via the same path as reassignment
- [x] 3.5 Tests: a single bad row rejects the whole file and changes nothing; over-deep row rejected; replace guard fires and then applies on confirm

## 4. Reassignment and staleness

- [x] 4.1 Implement `reassign_company_tree(session, company, new_tree_id)`: exact full-path re-resolution against the new tree, clear the rest, return the affected count — all in the caller's transaction
- [x] 4.2 Write one `AuditLog` row per affected line (`spend_tree_reassigned`, actor `system`, carrying `from_tree`/`to_tree`/`previous_spend_category_id`)
- [x] 4.3 ~~Use set-based UPDATEs, not per-row ORM writes.~~ **Reversed during implementation.** The audit rows need each line's *previous* `spend_category_id`, so the rows must be read into memory regardless — which removes most of the win — and `AuditLog.seq` is a DB-generated sequence that only applies because the ORM omits the column from its INSERT (see CLAUDE.md). A bulk insert is precisely the path that re-introduces the documented PostgreSQL `NotNullViolation`. Written as ORM writes over already-loaded rows; SQLAlchemy batches the UPDATEs. Revisit only with a PostgreSQL check that goes through the ORM.
- [x] 4.4 Tests: verified lines keep status and levels; an identical path re-resolves; nothing is requeued to `uncategorized`; audit rows are written

## 5. Spend tree API

- [x] 5.1 Add tree/node schemas to `src/web_api/schemas.py` (`SpendTreeRead` with node count + assigned companies, `SpendTreeDetailRead` with nodes, `SpendTreeCreate`, `SpendTreeUpdate`, `SpendCategoryRead`, `SpendCategoryCreate`, `SpendCategoryUpdate`, import request/response)
- [x] 5.2 Create `src/web_api/routers/spend_trees.py`: `GET /spend-trees`, `GET /spend-trees/{id}`, `POST /spend-trees` (clone or empty), `PATCH /spend-trees/{id}`, `POST /spend-trees/{id}/archive`, `POST /spend-trees/{id}/import`
- [x] 5.3 Add node endpoints: `POST /spend-trees/{id}/nodes`, `PATCH /spend-tree-nodes/{id}`, `DELETE /spend-tree-nodes/{id}`
- [x] 5.4 Gate reads on `tenant_scope` and writes on `require_management`; return 404 for any tree outside the caller's organization
- [x] 5.5 Refuse archiving a tree that a company is assigned, 409 naming the companies
- [x] 5.6 Register the router in `web_api/app.py`
- [x] 5.7 API tests covering each endpoint, both roles, and the cross-organization 404

## 6. Company wiring

- [x] 6.1 Accept optional `spend_tree_id` on `POST /companies`; validate it belongs to the org; when omitted call `ensure_default_tree` and assign — inside the existing single transaction
- [x] 6.2 Accept `spend_tree_id` on `PATCH /companies/{id}`; on change run `reassign_company_tree` in the same transaction and return the affected line count
- [x] 6.3 Add `spend_tree_id` + tree name to `CompanyRead`
- [x] 6.4 Tests: first company materializes the org default; second reuses it; a foreign tree is rejected and creates nothing; reassignment reports its count

## 7. Invoice line wiring

- [x] 7.1 Add `level_4` to `LINE_AUDIT_FIELDS`, `InvoiceLineVerify`, and `InvoiceLineRead`
- [x] 7.2 Add the computed `category_stale` field to `InvoiceLineRead` (`level_2 IS NOT NULL AND spend_category_id IS NULL`)
- [x] 7.3 In `verify_invoice_line`, resolve a supplied `spend_category_id` within the company's assigned tree and set `level_1..level_4` from its path, ignoring caller-sent levels; 422 for an unknown node or one from another tree
- [x] 7.4 Add the `stale` boolean filter to `GET /invoice-lines`, scoped like every other filter
- [x] 7.5 Add `level_4` to the `spend-by-category` group-by in `web_api/reporting.py`
- [x] 7.6 Tests: node correction beats sent levels; foreign node 422s; `level_4` appears in the audit diff; `?stale=true` returns exactly the stale set

## 8. AI pipeline

- [x] 8.1 Rewrite `ai_api/sync/categorizer.py`: `Category` carries a node id, full path and matching text; `_META` is removed in favour of candidates built from `SpendCategory` rows (keyword sets read from the template by node `code`)
- [x] 8.2 Add `build_candidates_from_tree(nodes)` and keep `default_candidates()` sourced from the template so existing categorizer tests still have a corpus
- [x] 8.3 In `ai_api/sync/runner.py`: load the company's assigned tree once per integration, delete `_spend_category_map()`, set `spend_category_id` from the matched node id, write `level_4`
- [x] 8.4 When a company has no resolvable tree, leave its lines `uncategorized`, record the reason on `SyncState`, and still advance the watermark
- [x] 8.5 Point `ai_api/rag/indexer.py` at a `SpendTree`'s nodes (collection keyed by tree id). **Added alongside the CSV path, not instead of it** — `build_index`/`load_accounts` are the PDF `InvoiceFlow`'s and synthdata's, not the sync's, and replacing them would break a pipeline outside this change's scope. New `build_tree_index`/`retrieve_categories` key on tree id; the CSV path retires when the embedding categorizer replaces the keyword stub.
- [x] 8.6 Tests: two companies with different trees are categorized against their own; a depth-4 match sets `level_4`; no tree leaves lines uncategorized with the ledger still persisted

## 9. Frontend — data layer and tree selector

- [x] 9.1 Add `spend_tree_id`, `level_4`, `category_stale` to `frontend/src/lib/types.ts`
- [x] 9.2 Create `frontend/src/lib/spend-trees.ts`: query options for the tree list and detail, mutations for create/clone/import/patch/archive and node CRUD
- [x] 9.3 Build `frontend/src/components/spend-tree/tree-selector.tsx` — a solid bordered trigger showing the current full path, opening a popover with level-columns filling left to right, plus a search that switches to a flat list of matching full paths
- [x] 9.4 Make the selector handle 3- and 4-level trees with no layout change, and allow choosing a non-leaf node
- [x] 9.5 Tests for the selector: picking sets the whole path; search reaches a depth-4 leaf; keyboard navigation works

## 10. Frontend — line category editor

- [x] 10.1 Rewrite `components/entries/line-category-editor.tsx` around the tree selector; remove the `level_1`/`level_2`/`level_3` text inputs
- [x] 10.2 Send `{ spend_category_id }` on save and read the levels back from the server response
- [x] 10.3 Mark a stale line as needing review, showing the stored path as the previous decision and distinguishing it from `ai_failed`
- [x] 10.4 Handle the no-tree case: state that no spend tree is assigned and link to company settings; keep description, amount, status and rationale visible
- [x] 10.5 Update `voucher-lines-tab`, `voucher-details-tab`, `voucher-drawer` and their tests for the new editor and `level_4`

## 11. Frontend — settings

- [x] 11.1 Add the `/settings/spend-trees` route and its navigation entry
- [x] 11.2 Build the tree list panel: name, depth, source, node count, assigned companies, with loading/empty/error states
- [x] 11.3 Build the create dialog with three starting points — clone, empty, CSV import — including name and max-depth selection
- [x] 11.4 Build the CSV import flow: parsed row count before applying, per-row errors with line numbers on rejection, explicit confirmation for a replace that would orphan lines
- [x] 11.5 Build the node editor: expandable hierarchy, add child, rename, reorder, edit description/code, delete — with add-child unavailable at max depth and delete confirmations stating child and line counts
- [x] 11.6 Add the spend-tree picker to company settings, with a post-save result stating the affected line count, that the values are kept, and linking to the stale backlog. **The warning before saving states the consequence but not the count** — the count only exists server-side and there is no dry-run endpoint; adding one was out of scope, so the exact number is reported the moment it is known instead of guessed at beforehand.
- [x] 11.7 Gate every mutating control behind the management role using the existing disabled-with-reason treatment
- [x] 11.8 Tests for the settings section, the import error path, and the reassignment confirmation

## 12. Verification

- [x] 12.1 `uv run pytest` green
- [x] 12.2 Frontend tests green (`./node_modules/.bin/vitest run` from `frontend/`)
- [x] 12.3 `uv run alembic upgrade head` on an empty PostgreSQL, then `downgrade` one revision, then `upgrade` again
- [x] 12.4 End-to-end by hand: create a company → default tree appears → clone it to a 4-level custom tree → assign it → confirm the stale count → correct a line through the tree selector and confirm `spend_category_id` resolves
- [x] 12.5 Update `CLAUDE.md` with the spend-tree section (org-owned trees, default template copy, depth rule, staleness rule)
