## Context

The categorizer is an LLM that picks one numbered candidate from the company's
assigned spend tree (`ai_api/sync/llm_categorizer.py`), called per line by
`_categorize_pending` in `ai_api/sync/runner.py`. Its design is sound: index-based
selection, no string snapping, outage separated from judgement. Its **inputs are
broken**.

Measured on the live dev database, not inferred:

| fact | value |
| --- | --- |
| lines total | 40 |
| lines with `item_name` | 38 |
| lines with `description` | 12 |
| lines the prompt can see text for | **12** |
| `ai_failed` | 9 |
| vendors with a `description` | **0 of 47** |

`_categorize_pending` builds `LineContext(description=ln.description, …)`. The
`item_name` migration moved the text and nulled `description`. So for 26 lines
the prompt states a supplier and an amount, and the model — correctly, and in
writing — says so.

Every one of the nine failures reads the same way. `DSB 1' Commute20`,
`DJI Osmo Nano actionkamera 128GB`, `EK-CryoFuel Clear (Premix 1000mL)`,
`alibaba.com`. All legible. None sent.

The reference implementation is `~/repos/groundley-ai`
(`src/llm_api/rag/spend/`, `src/llm_api/prompts/spend/default.py`): a production
spend categorizer with a two-stage retrieval pipeline, a supplier-description
prompt, an exact/fuzzy/semantic result cache keyed by tree hash, and accounting
rules encoded as prompt instructions. We take its ideas, not its shape — it is
async, OpenAI-embedded, MongoDB-backed and batch-oriented, and we are a
synchronous per-line sync against a local vLLM.

**Constraints that hold throughout:** `web_api` may never import `ai_api`; the
categorizer must work with `VLLM_TEMPERATURE=0.0` on a small local model; guided
decoding is banned (prompt-for-JSON + `parse_model`); no test may require a model
or a network.

## Goals / Non-Goals

**Goals:**

- The categorizer sees what the platform knows about a line — starting with its
  name, which is the field that always exists.
- A rename of a categorizer input field breaks a test, not a rationale.
- A supplier is a described business, not three opaque letters.
- The prompt encodes accounting judgement, not just "pick one".
- Doubt is a number a reviewer can filter on, not a red failure badge.
- A tree with a hole in it says so, with evidence, instead of quietly producing
  bad categorizations for months.
- Cost per line falls, because most lines are repeats of a line we have answered.

**Non-Goals:**

- **No fine-tuning and no evaluation harness in this change.** Groundley has both
  (`src/lines_finetune`, `spend_eval_results`). We have 40 lines. A benchmark
  built on 40 lines measures noise, and the honest first move is to fix the
  inputs and look again.
- **No reranker service.** Groundley's `rerank.py` is a second model between
  retrieval and selection. At our tree sizes the selection model *is* the
  reranker.
- **No batch API.** Groundley routes above a threshold into a batch endpoint. Our
  runs are tens of lines against a local server.
- **No rewriting of existing categorizations.** The nine failures go back through
  `POST /companies/{id}/recategorize`, which exists for exactly this.
- **No migration of existing trees** to the expanded template.

## Decisions

### 1. `item_name` is the line's text; `description` is an annotation on it

The prompt states `Item: <item_name>` and, only when it says something else,
`Detail: <description>`. Not a coalesce (`item_name or description`): both can be
present and mean different things, and a coalesce would silently drop the
description on every line that has both.

*Alternative rejected — rename the `LineContext` field to `item_name` and be
done.* That fixes today and re-arms the same trap: the bug was not the field's
name, it was that nothing tested the mapping. The field rename happens **and** a
runner-level test pins it.

### 2. The mapping gets a test that goes through the runner

`test_sync_spend_tree.py:219` constructs `LineContext(description=line.description)`
*inside the test* — it mirrors the runner's mapping rather than exercising it, so
it agreed with the bug. The new test persists an `InvoiceLine`, calls
`_categorize_pending` with a `complete` stub that captures the prompt, and asserts
the item name appears in it. It is the only test that can fail on a rename.

### 3. The model must answer; confidence carries the doubt

Withdrawing `0` is the decision with the most downside, and it is the user's
call, made knowingly. The honest record: **this is the failure mode that killed
the keyword matcher** — a bank fee filed under *Telecom* because "plan" is a
telecom keyword.

Four things make it a different bet now:

1. The model sees the item text. The keyword matcher's failure was a decision
   made on a token; this one is made on a sentence.
2. The supplier is described. Most forced-guess disasters are "unknown supplier,
   no text" — precisely the case enrichment removes.
3. The answer carries a confidence, and low confidence routes to review. A wrong
   answer nobody looks at is the danger; a wrong answer in a review queue is a
   task.
4. Phase 4 fixes the *cause* of the honest decline. Declining protected against a
   tree with no home for the line; the gap suggester repairs the tree instead of
   leaving the line stranded forever in a status the sync never revisits.

`ai_failed` narrows to a genuine fault — an index we never offered, or no
candidate set at all. That is a status worth having, and it is currently
overloaded with "the model was being careful".

### 4. Retrieval narrows within the tree, and only downward

Two-stage: embed the line text → `retrieve_categories(tree_id, top_k)` →
**expand each hit to its siblings** (groundley's `build_candidates` with
`expansion="level_2"`) → offer that set. Sibling expansion matters: retrieval
finds *Airfare*, and the answer is often *Ground Transport* next to it.

Two guards, both because a narrowed set is invisible when it is wrong:

- **Skip narrowing on small trees.** Groundley bypasses when
  `tree_size < 2 * top_k`. Our default tree has 18 leaves; narrowing it to 15
  spends an embedding call to remove three candidates and risks removing the
  right one. Below the threshold, offer everything.
- **Degrade to the full leaf set,** never to an empty set and never to another
  taxonomy. `retrieve_categories` already returns `[]` for an unindexed tree, and
  `[]` must mean "offer all", not "categorize nothing".

Index maintenance is `build_tree_index`, called at sync start for the assigned
tree; it is already idempotent by node count.

### 5. The cache key includes a tree hash, and lives in Postgres

Key: `(normalized item text, supplier id, native account code, tree hash)`.
Value: the chosen node id, confidence and rationale.

The tree hash is the part that is easy to leave out and fatal to leave out: a
customer renames a node, every cached answer still points at the old shape, and
the cache serves stale categorizations indefinitely with no way to notice.
Groundley hashes the category content (order-independent, content-only) and we
do the same over the *candidate set actually offered*.

*Alternative rejected — Qdrant semantic cache (groundley's `HYBRID` mode).* A
near-miss cache hit is a wrong category with a rationale describing a different
purchase. Exact-key first; semantic later, if the hit rate warrants it.

Postgres rather than Qdrant because it is an exact keyed lookup, it must be
transactional with the sync, and it must survive a Qdrant wipe.

### 6. Supplier enrichment is a separate stage, opt-in, and never blocks a sync

`web_context.py` already scrapes and summarizes, keyless, with a file cache. It
becomes a stage that fills `Vendor.description` for vendors that have none — not
an inline call inside `_categorize_pending`, which would put a web scrape on the
per-line path and make a slow network look like a slow categorizer.

Governed by an env flag defaulting to **off**, exactly as `FX_ENABLED` is, so the
suite and offline runs make no outbound request. A failure writes nothing and
fails nothing.

`Vendor` is global. A description written here is visible to every tenant, which
is the point (one lookup serves all) and the constraint (it must describe the
supplier's trade and nothing tenant-specific). A human-set description is never
overwritten — tracked by a nullable `description_source` on the vendor rather than
by the per-field `verified_fields` machinery, which is scoped to invoices and
lines and would be a strange thing to grow onto a global catalog row.

### 7. The gap suggester reads the database, writes proposals, and touches no tree

New `ai_api/suggestions/`, run as its own stage like `ai_api.documents.runner`:
group a company's low-confidence `ai_categorized` lines by similarity, ask the
model what category would have fitted them, and check the answer is not already
in the tree. Output is `SpendCategorySuggestion` rows — proposed name,
description, `parent_id`, rationale, evidence line ids, state.

**It never writes a `SpendCategory`.** `web_api/spend_trees/service.py` is the
only writer of that table (a rename rewrites every descendant's materialized
path), and acceptance goes through the existing node-creation endpoint. So the
suggester lives in `ai_api`, respects the one-way dependency, and cannot corrupt
a path.

A dismissed suggestion is remembered so it is not re-proposed each run. A
suggestion whose parent has since been deleted is not acceptable.

### 8. The review threshold is configuration, not a column

`needs_review` and the payload flag are computed on read from
`status == ai_categorized AND confidence < threshold`, the same discipline as
`category_stale` and `lines_reconciled`. A stored flag is a snapshot of a setting;
the setting will be tuned, and every historical line must move when it is.

### 9. The prompt lives in one reviewable function, and gains a skill

`build_prompt` stays public precisely so a prompt change is reviewable on its
own. The accounting rules go in as instructions, lifted in substance from
groundley's template.

Reason-before-JSON is compatible with our parser: `parse_model` already extracts
JSON from surrounding prose, which is what makes this free. It is worth checking
against the local model — a small model asked to reason sometimes never reaches
the JSON — and the fallback is to keep the rules and drop the reasoning
instruction.

Alongside it, a project skill (authored with `engineering-skills`) captures the
house rules for this kind of work: index-not-name, decline-vs-fault, prompt-for-
JSON over guided decoding, and the requirement that a prompt-input change be
pinned by a test through the caller. The value is that the next person changing
this prompt inherits the reasoning rather than rediscovering it from a rationale
in a screenshot.

## Risks / Trade-offs

**Forcing an answer puts wrong categories into the reports** → The review filter,
the confidence on every line, and the gap suggester. Measured, not assumed: after
phase 1 the failure set is re-run and the confidence distribution recorded before
phase 2 lands. If forced answers land confidently wrong, that is visible in
review throughput, and `0` is one prompt edit away.

**Enrichment scrapes the public web and writes to a global, cross-tenant table**
→ Off by default; the description states the supplier's trade only; a human's
description is never overwritten; a failure is a no-op. The blast radius of a bad
description is a worse prompt, not a wrong write to a customer's ledger.

**Retrieval hides the right answer** → Sibling expansion, the small-tree bypass,
and degradation to the full set. The number narrowed away is logged per run, as
groundley does, so a bad `top_k` is visible rather than inferred.

**The cache serves a stale answer after a tree edit** → The tree hash is in the
key. A change that alters the candidate set alters the hash and misses.

**The suggester proposes noise, and a reviewer accepts it** → It needs a group of
lines, never one; every proposal carries its evidence; a human accepts; a
dismissal is remembered. A tree that grows a node per odd purchase is worse than
one with a gap.

**This is four phases in one change** → They are independently shippable in the
stated order and the tasks are grouped that way. Phase 1 alone fixes the reported
bug and is a handful of lines; nothing later is a prerequisite for it.

## Migration Plan

1. **Phase 1** ships alone: the mapping fix, its test, and the prompt rules. Then
   `POST /companies/{id}/recategorize` requeues the nine `ai_failed` lines and the
   result is inspected against the invoices — a real before/after on real data.
2. **Phase 2** adds forced choice + lifecycle narrowing (one migration is not
   needed — no column changes; `ai_failed` simply stops being written for
   declines), then vendor enrichment behind its flag, then the review filter.
3. **Phase 3** wires the index and the cache. One migration for the cache table.
   Qdrant already runs in `docker compose`.
4. **Phase 4** expands the template at a new `TEMPLATE_VERSION` (existing copies
   untouched, asserted by test), then adds the suggester and its surface.

**Rollback:** phases 2–4 are each behind either a flag or a status decision that
reverts by prompt edit; the cache is dropped by truncating one table; the template
version is not retroactive, so nothing to undo.

## Open Questions

- **Does the local model reason-then-JSON reliably at temperature 0?** To be
  answered by running phase 1's prompt against the nine failures before phase 2.
  Fallback: keep the rules, drop the reasoning instruction.
- **What review threshold?** Provisionally 0.6, to be set from the confidence
  distribution once the model can actually see the lines — picking it now would be
  picking it from numbers produced by a blind categorizer.
- **Is `Vendor.description` the right home for enrichment, given `Vendor` is
  global and shared?** It is the field that exists and it is what the categorizer
  needs. If tenant-specific supplier notes are ever wanted, they are a different
  column on a different table, not a change here.
