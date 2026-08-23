## Why

**The categorizer has been blind since the `item_name` migration.** `_categorize_pending`
builds its prompt from `ln.description`, and the migration that introduced
`InvoiceLine.item_name` moved every line's text out of `description` and left it
null. On the live dev org that is **26 of 40 lines** whose only stated fact is a
supplier and an amount. The DSB rationale that prompted this change —

> *"The invoice line only provides the supplier name (DSB) and the amount
> (5780.00 DKK) without any description of the goods or services provided."*

— is not the model failing. It is the model reporting, accurately, that we asked
it to categorize `DSB 1' Commute20` without telling it about `DSB 1' Commute20`.
Every one of the nine `ai_failed` lines is the same story: `DJI Osmo Nano
actionkamera 128GB`, `EK-CryoFuel Clear (Premix 1000mL)`, `alibaba.com` — each
one legible, none of it sent.

**No test could have caught it.** Every categorizer test constructs
`LineContext(description=…)` by hand; `test_sync_spend_tree.py` even mirrors the
runner's mapping *inside the test*. Nothing exercises `InvoiceLine → LineContext`,
which is precisely the seam that broke.

Fixing the one-line mapping restores what we had. It does not make the
categorizer good. `~/repos/groundley-ai` has a production spend categorizer whose
prompt and retrieval design answer the parts we have never built: a supplier
*description* (all 47 of our vendors have an empty one), embedding retrieval
before the model sees the tree, a result cache, and real accounting rules about
fees, packaging and professional services.

## What Changes

**Phase 1 — stop the blindness** (the actual bug)

- `_categorize_pending` sends the line's **item name** as its primary text, with
  `description` as supplementary detail rather than a replacement.
- A runner-level test asserts the `InvoiceLine → LineContext` mapping field by
  field, so a future column rename fails here instead of in a rationale.
- The prompt gains groundley's accounting rules (a fee/tax/toll goes to fees
  regardless of supplier; packaging goes to packaging; a product bought as part
  of a professional service follows the service; a bare "discount" follows the
  supplier) and asks the model to reason *before* emitting JSON.

**Phase 2 — give the model something to reason with**

- **BREAKING (behavioural):** the model **must return a category**. `0`/"none of
  these fit" is withdrawn as an answer. Confidence carries the doubt instead, and
  a low-confidence line is queued for human review rather than reported as a
  failure. `ai_failed` narrows to what it should always have meant: the model
  answered with something that is not one of the candidates we offered, or did
  not answer at all.
- `Vendor.description` is filled once per supplier from web context
  (`ai_api/web_context.py`, built and unused), and carried into the prompt. Buyer
  context comes from the company. "DSB — Danish State Railways" ends the DSB
  question before the taxonomy is even read.
- `GET /invoice-lines?needs_review=true` returns AI results below a confidence
  threshold, so "low confidence is the review signal" is something a reviewer can
  actually act on.

**Phase 3 — make it hold at customer scale**

- Two-stage candidate selection: embed the line, retrieve the top-K nodes from
  the tree index, expand to their siblings, and offer *those* to the model.
  `build_tree_index`/`retrieve_categories` already exist and are unwired. At 18
  leaves this changes nothing; at a customer's 500-leaf tree it is the difference
  between a usable prompt and an unusable one. It degrades to the full leaf set
  whenever retrieval is unavailable — never to a different taxonomy.
- A result cache keyed by (item text, supplier, account, **tree hash**) so a
  monthly DSB ticket is one model call, not twelve. The tree hash is in the key
  because a customer editing their taxonomy must invalidate every answer.

**Phase 4 — the taxonomy itself**

- The default template gains the leaves real spend lands on, starting with
  **Ground Transport** (rail, bus, taxi) — the one the DSB ticket needed — plus
  bank & payment fees, insurance, and subscriptions. `TEMPLATE_VERSION` is
  bumped. Existing organizations hold *copies* and are deliberately not migrated.
- **New:** an AI **category-gap suggester** reads a company's spend and its tree
  and proposes categories the tree is missing, evidenced by the lines that fit
  nowhere well. Low-confidence categorizations are its input signal. Suggestions
  are proposals a human accepts or dismisses — nothing writes a tree node
  unattended.

## Capabilities

### New Capabilities
- `spend-categorization-model`: what the categorizer is told, how a candidate is
  chosen and returned, what confidence means, and how retrieval and caching
  narrow the question — the contract the sync runner calls into.
- `supplier-enrichment`: filling the global vendor catalog's `description` from
  web context, once per supplier, cached and correctable.
- `spend-tree-gap-suggestions`: proposing categories a company's tree is missing,
  evidenced by its own spend, for a human to accept or dismiss.

### Modified Capabilities
- `sync-pipeline-orchestration`: the line→prompt mapping must carry the item
  name; candidates come from retrieval when it is available.
- `categorization-lifecycle`: a categorization always resolves to a category;
  `ai_failed` narrows to a genuine fault; low confidence is a review signal.
- `spend-tree-management`: the default template gains ground transport, fees,
  insurance and subscription leaves, at a new template version.
- `web-api-invoice-review`: `/invoice-lines` gains a low-confidence review filter.
- `frontend-settings`: spend-tree settings surface the gap suggestions.

## Impact

**Code** — `ai_api/sync/runner.py` (`_categorize_pending`),
`ai_api/sync/llm_categorizer.py` (prompt, forced choice, cache),
`ai_api/sync/categorizer.py` (candidate construction), `ai_api/rag/indexer.py`
(wiring the existing tree index), `ai_api/web_context.py` (supplier enrichment),
new `ai_api/suggestions/` (gap suggester), `web_api/spend_trees/template.py`
(new leaves, version bump), `web_api/routers/invoice_lines.py` (review filter),
`web_api/db/models/` + one migration (suggestion rows, vendor enrichment stamp),
`frontend/src/routes/_authed/settings/spend-trees*`.

**Data** — no existing categorization is rewritten. The nine `ai_failed` lines
are requeued through the existing `POST /companies/{id}/recategorize`, which is
exactly the transition it was built for.

**Dependencies** — Qdrant (already in `docker compose`) becomes load-bearing for
phase 3 rather than optional; the fallback to the full leaf set keeps a sync
working without it. Supplier enrichment makes outbound web requests and is
therefore opt-in by env flag, like `FX_ENABLED`.

**Risk, stated plainly** — forcing an answer is what the keyword matcher did when
it filed a bank fee under *Telecom*, and that failure is why declining exists.
Three things are different now: the model sees the item text (it did not), the
supplier is described (it was not), and a forced answer carries a confidence that
routes it to review. Phase 4's gap suggester is the systematic answer to the case
declining was protecting — a tree with no home for the line — and it fixes the
tree instead of leaving the line uncategorized forever.
