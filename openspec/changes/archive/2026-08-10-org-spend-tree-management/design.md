## Context

The spend tree is the target taxonomy of the whole product, and today it is effectively unimplemented. Three facts describe the current state:

- `SpendCategory` rows carry `company_id` and four denormalized `level_*` columns and nothing else — no parentage, no ordering, no identity beyond the level strings. Nothing seeds them, so in practice the table is empty.
- `_spend_category_map()` in `ai_api/sync/runner.py` keys nodes by `(level_2, level_3)`. Against an empty table it returns `{}`, so `InvoiceLine.spend_category_id` is null on essentially every categorized line. The categorization "works" only because the levels are copied onto the line as strings.
- The taxonomy the categorizer actually uses is `_META`, a 19-entry dict hard-coded in `ai_api/sync/categorizer.py`, keyed by a *mock ERP account code*. It is not a spend tree; it is a mock chart of accounts wearing one.

The customers are EU mid-market SMBs and the bookkeeping firms that serve them. A firm running eight client companies wants one taxonomy across the group. A manufacturer wants a fourth level under `Direct`. Neither is expressible today.

Constraints that shape everything below:

- **Dependency direction is one-way.** `ai_api` imports the domain from `web_api`; `web_api` must never import `ai_api`. The tree is domain, so it lives in `web_api` and the categorizer reads it.
- **Migrations are one squashed baseline.** This change adds the second revision in the chain, and `tests/web_api/test_migrations.py` runs it from base against a real PostgreSQL.
- **`SpendCategory` is referenced by `InvoiceLine.spend_category_id`.** Dropping `company_id` is a real FK-bearing table change, not a rename.
- **Provenance decides affordance** (the voucher panel's governing rule). The category is AI-produced, so it stays correctable — but "correctable" has meant free text, and free text is the wrong control for a value that must resolve to a row.

## Goals / Non-Goals

**Goals:**

- A `SpendTree` owned by the `Organization`, assigned per `Company`, so one taxonomy can serve a group and different subsidiaries can differ.
- A shipped default template, three levels, `Direct`/`Indirect` at level 1, **copied** into an org on first use so a tenant can edit its copy freely.
- Custom trees to four levels, with the depth limit enforced at write time.
- Three authoring paths — clone, from scratch, CSV import — producing identical node rows.
- `spend_category_id` that actually resolves, because the reviewer picks a node instead of typing three strings.
- Reassignment that keeps every stored value and marks the consequence, rather than rewriting or requeueing.

**Non-Goals:**

- Bulk re-categorization of history against a new tree. The stale flag is the signal; the action is a follow-up.
- Per-node keyword/synonym curation in the UI. The categorizer's matching text stays name + code + description for now.
- Tree versioning and diffing beyond `template_version` on the copy.
- Replacing the deterministic keyword categorizer with the Qdrant/LLM one. This change makes the *candidate set* real; the matcher is unchanged.
- Moving `ErpAccount → SpendCategory` mapping into a stored rule table.

## Decisions

### 1. Adjacency list plus a materialized path, not one or the other

`SpendCategory` gains `parent_id`, `depth`, `name`, `sort_order`, `code` — and **keeps** `level_1..level_4` as a materialized path maintained on write.

The adjacency list is what makes the thing a tree: renaming, reparenting, ordering siblings, and enforcing depth all need real parentage. The materialized path is what keeps every existing read working — `InvoiceLine.level_*`, `reporting.spend-by-category`, the entries table, the audit diffs — without a recursive CTE on every query. A categorization result is a *snapshot of a path at a point in time* anyway; it must survive independently of the node it came from, which is exactly what the stale rule requires.

The cost is a write-time invariant: a rename or reparent rewrites the descendants' paths in the same transaction. That is bounded (a tree is hundreds of nodes, not millions) and it is one function, `_rewrite_paths(session, node)`, called from every mutation.

*Alternative rejected — path only (today's model).* No parentage means no ordering, no reparent, no depth enforcement, and "the same node" is a tuple of strings that a rename silently forks.
*Alternative rejected — adjacency only.* Every read of a line's category becomes a tree walk, and a deleted node erases what a human verified. Unacceptable given lines must keep their decision.
*Alternative rejected — `ltree`/closure table.* Real depth is capped at 4. The machinery costs more than it buys and `ltree` is PostgreSQL-only, while the test suite runs on SQLite.

### 2. The default tree is a code-resident template, copied on first use

The template lives in `web_api/spend_trees/template.py` as plain data with a `TEMPLATE_VERSION` string. `ensure_default_tree(session, organization_id)` returns the org's `source='default_template'` tree, creating and seeding it if absent. It is called from company creation and from the sync when a company has no assignment.

Copy-on-use rather than a shared global row, because a customer will rename `Facilities & Office` on day two and that must not touch anyone else. Copy rather than eager creation at org-provisioning time, because JIT provisioning in `deps.py` creates orgs from a Clerk token and should not be doing taxonomy work.

`template_version` is recorded but nothing acts on it yet — it is the hook for "your tree is based on v1, v2 adds three nodes" later, and costs one column now.

*Alternative rejected — seed from `ErpAccount`.* The chart of accounts is the ERP's shape, not a spend taxonomy; the whole point of `SpendCategory` being distinct from `ErpAccount` is that the categorizer bridges the two.

### 3. `max_depth` on the tree, checked on write

`SpendTree.max_depth` is 3 or 4; `default_template` trees are pinned to 3. A node write computes `depth = parent.depth + 1` and rejects `> max_depth` with 422. Raising 3→4 is free; lowering is refused while deeper nodes exist.

Putting the limit on the tree rather than deriving it from the deepest existing node makes the UI honest: the editor can gray out "add child" *before* the user tries, which is the affordance rule the frontend spec already commits to.

### 4. Reassignment is a transactional side effect of the company update, not a background job

`PATCH /companies/{id}` with a new `spend_tree_id` runs, in the same transaction:

1. re-resolve every line of that company whose stored `level_*` path matches a node in the new tree **exactly** (case-sensitive, full path) → point at that node;
2. clear `spend_category_id` on the rest;
3. one `AuditLog` row per affected line, action `spend_tree_reassigned`, actor `system`, carrying `{from_tree, to_tree, previous_spend_category_id}`;
4. return the affected count.

Exact matching only. Fuzzy matching here would be the same guessing the sync's derived entry→line link explicitly refuses, and getting it wrong reassigns a human's verified category to a different node without anyone noticing.

Synchronous because the caller must learn the consequence at the moment they cause it — a dialog saying "this leaves 412 lines needing review" is the whole safety of the feature. A company's line count is bounded by its ledger; if this ever becomes slow the fix is a job with a progress endpoint, not silent asynchrony.

*Alternative rejected — requeue affected lines to `uncategorized`.* Destroys human verifications, which is precisely what the audit-log groundwork in the extraction stage exists to avoid.

### 5. Staleness is computed, not stored

`category_stale` is `(level_1 IS NOT NULL OR level_2 IS NOT NULL) AND spend_category_id IS NULL` — a line that has a decision but no resolving node. No column, no second thing to keep in sync, and it is automatically correct after any reassignment, node deletion, or import replace.

"Any level recorded" rather than `level_1` alone: a tree node's path always starts at level 1, but lines categorized *before* spend trees existed carry a `level_2` with no `level_1`, and those are precisely the lines that most need reviewing.

The subtlety: an `ai_failed` line has neither, so it is not stale; a line categorized before any tree existed *is* stale, which is correct — its category resolves to nothing and someone should look at it.

This makes `?stale=true` a plain `WHERE` clause and `InvoiceLineRead.category_stale` a computed field, with no join to the tree at read time.

### 6. The candidate set is built from persisted nodes; `_META` becomes template seed data

`categorizer.build_candidates()` currently takes `ErpAccountData`. It gains a sibling that takes `SpendCategory` rows: `Category(node_id, path, matching_text)`. The runner loads the company's assigned tree once per integration and passes the candidates down; `_spend_category_map()` disappears, since a match now carries the node id directly.

`_META`'s content moves to `web_api/spend_trees/template.py` as the default template's node definitions plus their keywords. The keyword sets are the one thing a persisted node has no column for — for now they are attached to template-seeded nodes by `code`, and a custom node matches on its name/description tokens alone. That is a known weakness of the *stub* matcher, and it disappears when the Qdrant/LLM categorizer lands, which embeds `name + description` and needs no curated synonyms.

A company with no resolvable tree leaves its lines `uncategorized` and records the reason on `SyncState`. Falling back to a built-in taxonomy the customer never chose would produce categories nobody can trace.

### 7. CSV import validates wholly, then writes wholly

Parse → validate every row → build the intended node set in memory → diff against existing → apply. Validation covers: depth vs `max_depth`, path gaps (`level_3` with no `level_2`), duplicate sibling paths, duplicate `code`. Errors are returned per row with the file's line number.

`mode=merge` adds and updates; `mode=replace` also removes. A replace that would remove nodes referenced by invoice lines returns 409 with the affected count unless `confirm=true`. Removal then clears those lines' pointers by the same path as reassignment — the lines go stale, they do not lose their levels.

### 8. The tree selector is a column browser inside a popover, built on the existing primitives

`@base-ui-components/react` popover + the existing `Command`-less `combobox.tsx` pattern. The control is a button showing the current full path; clicking opens a panel with **columns**, one per level, filling left to right as you pick — the shape that makes a 4-level taxonomy navigable without a scrolling accordion — plus a search input above them that switches the panel to a flat list of matching full paths.

Columns rather than an indented accordion because the tree is wide and shallow (hundreds of nodes over 3–4 levels); an accordion of 19 level-2 nodes each with 5 children is a scroll-hunt, while three columns are two clicks. The whole tree arrives in one request (`GET /spend-trees/{id}`), so navigation and search are client-side and instant.

Per the "UI needs visual weight" constraint: the control is a solid, bordered trigger showing the path with level separators — not a pale ghost input — and the chosen path reads back as weighted text with the leaf emphasized, so the current answer is the visual anchor of the editor.

Saving sends `{spend_category_id}` only. The server derives the levels. This is what makes a correction always resolve.

### 9. `level_4` lands on `InvoiceLine`, `LINE_AUDIT_FIELDS`, and the verify schema

Straightforward but easy to half-do: the column, `InvoiceLineRead`, `InvoiceLineVerify`, `LINE_AUDIT_FIELDS`, and `reporting.spend-by-category`'s group-by all need it, or a four-level tree produces results that are invisible somewhere.

## Risks / Trade-offs

**Dropping `spend_categories.company_id` is a breaking schema change** → Migration creates `spend_trees`, adds the new node columns, then for each distinct `company_id` present creates one `custom` tree in that company's organization, moves its nodes onto it, back-fills `parent_id`/`depth`/`name` from the level path, and assigns the company. In practice the table is empty or near-empty, but the migration must not assume that. Rollback is a downgrade that recreates `company_id` from the tree's first assigned company — lossy if a tree ended up shared, which is stated in the migration docstring.

**Materialized paths can drift from `parent_id`** → Every mutation goes through one service module (`web_api/spend_trees/service.py`); nothing writes `SpendCategory` directly. A test asserts path-equals-walked-path after rename, reparent, and import.

**Exact-match re-resolution will feel arbitrary to users** ("I renamed one node and now 300 lines are stale") → The confirmation dialog states the count before saving, and the entries view links straight to the stale backlog. Fuzzy matching is deliberately not the mitigation.

**The reassignment transaction touches every line of a company** → Bounded by ledger size and executed as set-based UPDATEs, not per-row ORM writes, with the audit rows inserted in one `bulk_insert_mappings`. If a large tenant makes this slow, the escape hatch is a job endpoint; the API shape (returning an affected count) does not change.

**Keyword quality drops for custom nodes** → Custom trees match on name/description tokens only, so the stub categorizer will be weaker on them than on the default. Accepted: the stub is explicitly a stand-in, and the change is what finally gives the real categorizer a per-tenant corpus to embed.

**Qdrant collections are keyed `spend_tree_{tenant_id}` from a CSV** → `rag/indexer.py` moves to indexing a `SpendTree`'s nodes, keyed by tree id. Until the LLM categorizer lands this is unused by the sync path, so it can follow rather than block.

**Two trees, one org, one report** → Reports group by category path strings, which are comparable across trees only by accident. Not addressed here; noted so nobody reads a cross-company category report as authoritative when the companies use different trees.

## Migration Plan

1. **Schema** — one Alembic revision on top of `0001_baseline_schema`: create `spend_trees`; add `spend_categories.spend_tree_id`, `parent_id`, `depth`, `name`, `code`, `sort_order`; add `companies.spend_tree_id`; add `invoice_lines.level_4`. Data step migrates existing nodes onto per-company custom trees. Then drop `spend_categories.company_id`. `tests/web_api/test_migrations.py` runs it from base on PostgreSQL.
2. **Domain + service** — models, `web_api/spend_trees/` (template, service, import), schemas, routers. Endpoints ship read-only-safe: nothing else depends on them yet.
3. **Company wiring** — create/patch carry `spend_tree_id`; `ensure_default_tree` on create; the reassignment path.
4. **Line wiring** — `level_4`, `category_stale`, verify by node, `?stale=` filter.
5. **AI side** — candidates from the assigned tree; `_META` relocated to the template; `SyncState` reason when no tree.
6. **Frontend** — `lib/spend-trees.ts`, the tree-selector component, the settings section, company assignment, stale marking.

Rollback: the revision has a working `downgrade` (lossy as described). Steps 2–6 are additive behind the schema, so a partial deploy leaves companies on their default copy behaving as today.

## Open Questions

- Should a tree be shareable across organizations for a bookkeeping firm that runs several *orgs* rather than several companies? Out of scope now; the `organization_id` FK is what would have to relax.
- Should `code` be required on custom trees so CSV re-import can update by key rather than by path? Currently optional; path is the import key.
- Does the stale backlog deserve its own surface (a "needs review" queue) rather than a filter on the entries view? The filter ships first.
