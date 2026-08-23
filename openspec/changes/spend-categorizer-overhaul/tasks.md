## 1. Phase 1 — stop the blindness

- [x] 1.1 Write a failing test in `tests/ai_api/test_sync_runner.py` that persists an `InvoiceLine` with `item_name` set and `description` null, runs `_categorize_pending` with a `complete` stub capturing the prompt, and asserts the item name appears in it. Watch it fail against today's code.
- [x] 1.2 Rename `LineContext.description` to `item_name` and add a separate `description` field; update `_fact_lines` to state `Item:` and, only when it differs, `Detail:`. Update the existing `LineContext(description=…)` call sites in `tests/ai_api/test_llm_categorizer.py` and `test_sync_spend_tree.py`.
- [x] 1.3 Fix `_categorize_pending` in `ai_api/sync/runner.py` to pass `ln.item_name` and `ln.description` separately. Test 1.1 passes.
- [x] 1.4 Replace `test_sync_spend_tree.py:219`'s hand-mirrored mapping with a call through the runner, so no test agrees with a future mapping bug.
- [x] 1.5 Add the accounting rules to `_INSTRUCTIONS` (fee/tax/toll/levy outranks the supplier and freight is not one; packaging outranks the supplier; a product inside a professional service follows the service; a bare discount follows the supplier), with a test per rule using a stub `complete` that asserts the rule text is in the prompt.
- [x] 1.6 Add the reason-before-JSON instruction and a test that a reply of prose followed by JSON parses correctly through `parse_model`.
- [x] 1.7 Run the full suite; confirm no regression. Then requeue the nine `ai_failed` lines via `POST /companies/{id}/recategorize` against the live vLLM on `:8999` and record the before/after per line, including the confidence distribution, in the change folder as `phase1-results.md`.

## 2. Phase 2 — a forced answer, a described supplier, a review queue

- [x] 2.1 Write failing tests: the model always returns a category; an out-of-range index still yields `ai_failed` and is never snapped; an outage still leaves the line `uncategorized`.
- [x] 2.2 Rewrite `_INSTRUCTIONS` to require a category ("you must return a category, even if it is an estimate; express doubt as a low confidence"), drop the `0` option from `build_prompt`, and remove the `choice == 0` branch from `categorize_line`. Tests from 2.1 pass.
- [x] 2.3 Confirm `confidence` is set on every `ai_categorized` line and that `ai_failed` is now written only for an unoffered index or an absent candidate set; add a test asserting a "hard" line becomes `ai_categorized` with low confidence rather than `ai_failed`.
- [x] 2.4 Add `description_source` to `Vendor` (nullable: `web` / `human`) with an Alembic migration, and a test that a human-set description is never overwritten by enrichment.
- [x] 2.5 Add `ai_api/enrichment/` — a stage that finds vendors with no description, calls `web_context.get_buyer_context`-style summarization once per vendor, and writes `description` + `description_source='web'`. Guard behind `VENDOR_ENRICHMENT_ENABLED` (default false); add it to `.env.example`.
- [x] 2.6 Add a runnable entry point (`python -m ai_api.enrichment.runner`, with `--company-id` / `--limit`) and tests that cover: off by default makes no request; a failed lookup writes nothing and raises nothing; an already-described vendor is skipped.
- [x] 2.7 Carry the supplier description and the buying company's name/description into `LineContext` and the prompt; test that both appear.
- [ ] 2.8 Add `CATEGORIZATION_REVIEW_THRESHOLD` config (provisional 0.6) and a `needs_review` computed property on the line payload in `web_api/schemas.py`; test it follows the threshold and is never stored.
- [ ] 2.9 Add the `needs_review` filter to `GET /invoice-lines`, excluding `verified`, `uncategorized` and `ai_failed`; test it composes with `company_id` and the date range and paginates.
- [ ] 2.10 Update the frontend line badge so a low-confidence `ai_categorized` line reads as needing review rather than as a failure, and `ai_failed` reads as a genuine fault. Add the filter to the Entries filter bar.

## 3. Phase 3 — retrieval and cache

- [ ] 3.1 Add `build_candidates_from_retrieval(tree_id, query, full_candidates, top_k)` in `ai_api/sync/categorizer.py`: retrieve, expand each hit to its siblings, return the union. Pure over an injected retrieval function, so tests need no Qdrant.
- [ ] 3.2 Test the guards: a tree smaller than `2 × top_k` is not narrowed; an empty retrieval result yields the full leaf set, never an empty list; every returned candidate belongs to the requested tree.
- [ ] 3.3 Call `build_tree_index` for the assigned tree at sync start and wire retrieval into `_categorize_pending`; log per run the tree size, average candidates per line, and the reduction percentage, so a bad `top_k` is visible.
- [ ] 3.4 Add a `CategorizationCache` model (key columns: normalized item text, `vendor_id`, `native_account_code`, `tree_hash`; value: `spend_category_id`, confidence, rationale) with an Alembic migration and a unique constraint on the key.
- [ ] 3.5 Add `tree_hash(candidates)` — order-independent, content-only over the candidate set actually offered — and test that adding, renaming or removing a node changes it while reordering does not.
- [ ] 3.6 Wire the cache into `categorize_line` behind the model call; test that a repeated line costs one model call, that a tree edit invalidates it, and that two companies with different trees never share an entry.
- [ ] 3.7 Confirm a cached result is indistinguishable on the line from a fresh one (same fields, same audit row) and that the sync still works with Qdrant stopped.

## 4. Phase 4 — the taxonomy and its gaps

- [ ] 4.1 Add the missing leaves to `web_api/spend_trees/template.py`: `Travel & Entertainment > Ground Transport` (rail, bus, taxi), `Financial > Bank & Payment Fees`, `Financial > Insurance`, `Indirect > Subscriptions & Memberships`. Keep three levels and the closed `Direct`/`Indirect` root. Bump `TEMPLATE_VERSION`.
- [ ] 4.2 Test that a version bump does not touch an existing organization's copy — no nodes added, removed or renamed, `template_version` unchanged, no line made stale.
- [ ] 4.3 Add a `SpendCategorySuggestion` model (tree id, proposed name/description, `parent_id`, rationale, evidence line ids, state `pending|accepted|dismissed`) with an Alembic migration.
- [ ] 4.4 Add `ai_api/suggestions/` — group a company's low-confidence lines by similarity, ask the model what category would have fitted each group, discard any proposal already present in the tree, and write pending suggestions. Runnable as `python -m ai_api.suggestions.runner`.
- [ ] 4.5 Test the suggester: a group produces one suggestion, a lone odd line produces none, an existing category is never re-proposed, a dismissed suggestion is not re-proposed, and a run leaves the tree byte-for-byte unchanged.
- [ ] 4.6 Add `GET /spend-trees/{id}/suggestions` (any member) and `POST /spend-tree-suggestions/{id}/accept|dismiss` (management-gated). Accept creates the node through `web_api/spend_trees/service.py`, never by direct write. Test tenant scoping and that an orphaned parent makes a suggestion unacceptable.
- [ ] 4.7 Surface suggestions in the spend-tree editor at `/settings/spend-trees`: proposal, parent, reason, evidence lines linking to each line. Accept inserts the node in place without a reload; dismiss offers a session-scoped undo; a `viewer` sees evidence and no controls.

## 5. Capture the reasoning

- [ ] 5.1 Author a project skill with `engineering-skills` covering the house rules this change establishes: choose by index never by name, separate an outage from a judgement, prompt-for-JSON over guided decoding, state absent facts by omission, and pin every prompt input with a test that runs through the caller.
- [ ] 5.2 Update `CLAUDE.md` — the categorizer section (inputs, forced answer, retrieval, cache), a new supplier-enrichment note, the gap suggester, and the new env vars.
- [ ] 5.3 Full suite green: `uv run pytest`, `./node_modules/.bin/tsc --noEmit`, frontend vitest, and eslint at or below its current baseline.
