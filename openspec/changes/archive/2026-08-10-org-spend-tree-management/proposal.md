## Why

The spend tree is the target taxonomy every categorization lands in, yet today it is unmanageable: `SpendCategory` rows are scoped to a single company, no seeding path exists (`_spend_category_map()` is empty in practice, so `spend_category_id` is almost always null), and the only tree a categorizer really uses is a hard-coded `_META` table inside `ai_api/sync/categorizer.py`. A customer cannot see the taxonomy their spend is being sorted into, let alone change it.

That is the wrong shape for the customers we serve. A bookkeeping firm running several client companies wants one taxonomy across the group; a manufacturer wants its own tree with a fourth level under `Direct > Raw Materials`. And on the invoice slide-over, a reviewer correcting a category types free text into three inputs — a spelling that never matches a real node produces a categorization that resolves to nothing, silently.

## What Changes

- **New `SpendTree` entity, owned by the Organization.** A tree is a named taxonomy belonging to an org; a `Company` points at the tree it categorizes against (`Company.spend_tree_id`). One org may hold several trees and assign different ones to different companies.
- **`SpendCategory` is reparented from a company to a tree.** **BREAKING** — `spend_categories.company_id` is replaced by `spend_categories.spend_tree_id`. Nodes also gain real tree structure: `parent_id`, `depth`, `name`, `sort_order`, and a stable `code`, rather than four denormalized level columns being the only identity a node has. The `level_1..level_4` columns stay on the node as the materialized path so existing joins and reads keep working.
- **A built-in default tree, 3 levels deep.** A versioned platform template ships in code — level 1 is exactly `Direct` / `Indirect`, level 2 and level 3 are the standard taxonomy. It is **copied into the org on first use**, so an org can edit its copy without touching another tenant's.
- **Custom trees go to 4 levels.** The default template is capped at depth 3; a custom tree may declare `max_depth` of 4. Depth beyond the tree's declared maximum is rejected at write time, not silently truncated.
- **Three authoring paths**, all producing the same node rows: clone the default and edit it, build an empty tree from scratch, or import a CSV of `level_1..level_4` + description. Import validates the whole file and either applies it wholly or rejects it — a half-loaded taxonomy is worse than none.
- **`InvoiceLine` gains `level_4`.** A categorization against a 4-level tree has nowhere to record its leaf today. It joins `LINE_AUDIT_FIELDS`, `InvoiceLineVerify`, `InvoiceLineRead` and the reporting group-bys.
- **Switching a company's tree keeps history and flags it stale.** Stored `level_1..level_4` stay on the line as the evidence of what was decided; `spend_category_id` is cleared when it points into a tree the company no longer uses, and the line becomes visibly re-reviewable. Nothing is silently rewritten and no human verification is discarded.
- **The categorizer's candidate set comes from the company's assigned tree**, not from `_META`. The hard-coded table is demoted to the seed definition of the default template — one source of truth, in one place.
- **The line category editor becomes a tree selector.** On the invoice slide-over, correcting a category means picking a node from the company's tree — level by level, with search — instead of typing three free-text strings. Levels are derived from the chosen node, so a correction always resolves to a real `spend_category_id`.
- **New management UI** under Settings: list the org's trees, create/clone/import, edit nodes, and assign a tree to each company.

## Capabilities

### New Capabilities

- `spend-tree-management`: the org-owned `SpendTree` and its nodes — the default template and how it is copied, custom trees and their depth limit, the three authoring paths, per-company assignment, the staleness rule when an assignment changes, and the API surface for all of it.

### Modified Capabilities

- `domain-model`: `SpendTree` added; `SpendCategory` reparented from `company_id` to `spend_tree_id` and given real tree structure; `Company.spend_tree_id` added; `InvoiceLine.level_4` added.
- `categorization-lifecycle`: the categorization result carries `level_4`; the accepted `spend_category_id` SHALL resolve within the company's assigned tree; a line whose category belongs to a tree the company no longer uses is flagged stale rather than rewritten.
- `web-api-invoice-review`: `POST /invoice-lines/{id}/verify` accepts `level_4` and validates `spend_category_id` against the company's assigned tree; a correction naming a node outside that tree is rejected.
- `sync-pipeline-orchestration`: the sync builds its candidate set from the company's assigned spend tree instead of the built-in `_META` table.
- `web-api-company-management`: company create and update carry `spend_tree_id`; a company created without one is assigned the org's default-template copy.
- `frontend-settings`: a Spend trees section — list, create, clone, import CSV, edit nodes, assign per company.
- `frontend-erp-entries`: the voucher slide-over's line category editor is a tree selector over the company's tree, not three free-text inputs.

## Impact

**Schema** — new `spend_trees` table; `spend_categories` gains `spend_tree_id`, `parent_id`, `depth`, `name`, `code`, `sort_order` and drops `company_id`; `companies` gains `spend_tree_id`; `invoice_lines` gains `level_4`. One Alembic migration on top of `0001_baseline_schema`. Existing `spend_categories` rows are few-to-none in practice, but the migration still carries them onto a per-company tree rather than dropping them.

**`web_api`** — new `routers/spend_trees.py` and `spend_trees.py` service (template seeding, cloning, CSV import, depth validation); `schemas.py` (tree/node read+write shapes, `level_4` on line read/verify); `audit.py` (`level_4` in `LINE_AUDIT_FIELDS`); `routers/companies.py`, `routers/invoice_lines.py`; `reporting.py` where category group-bys run.

**`ai_api`** — `sync/categorizer.py` (candidates from persisted tree nodes; `_META` becomes the default-template seed data), `sync/runner.py` (`_spend_category_map` keyed by node id within the assigned tree, `level_4` written through), `rag/indexer.py` (index a tree's nodes rather than a CSV chart of accounts).

**Frontend** — new `lib/spend-trees.ts` query/mutation layer and a Settings route; `components/entries/line-category-editor.tsx` rewritten around a new tree-selector component; `lib/types.ts`, `lib/invoices.ts`.

**Not in scope** — re-categorizing history against a new tree (the stale flag is the signal; a bulk re-categorize action is a follow-up), per-node keyword/synonym curation in the UI, and tree versioning beyond the template's own version stamp.
