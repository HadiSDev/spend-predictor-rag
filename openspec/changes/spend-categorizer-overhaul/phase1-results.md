# Phase 1 results — the nine `ai_failed` lines, re-run against the real model

Measured against the live vLLM (`google/gemma-4-E4B-it` on `:8999`) over the
VectorLab ApS ledger. **Read-only**: the categorizer was driven directly with the
runner's own context-building; nothing was committed, so the lines are still
`ai_failed` and the requeue remains a deliberate later step.

Two runs, because the first produced a result worth checking.

## Before

All nine lines `ai_failed`, and every rationale said some version of the same
thing — that the line stated no goods or services. It did. We were not sending
them.

## After

| item name | supplier | run 1 | run 2 |
| --- | --- | --- | --- |
| `DSB 1' Commute20` | DSB | Ground Transport (0.9) | Ground Transport (0.9) |
| *(none)* | Aquatuning GmbH | declined | declined |
| `Plus` | Shine Denmark ApS | declined | declined |
| `EK-CryoFuel Clear (Premix 1000mL)` | EKWB | Cost of Goods Sold (0.9) | Cost of Goods Sold (0.8) |
| `EK-CryoFuel Loop Cleaner + Superflush` | EKWB | Cost of Goods Sold (0.9) | Cost of Goods Sold (0.9) |
| `1 Voksen` | DSB | **Utilities (0.7)** | **Ground Transport (0.9)** |
| `DJI Osmo Nano actionkamera 128GB` | ELGIGANTEN A/S | Office Equipment (0.8) | Office Equipment (0.8) |
| `Antal Produkt` | DSB | declined | declined |
| `alibaba.com` | FULUO FLAVOR & FRAGRANCE | declined | declined |

**5 of 9 categorized**, in both runs. Latency 5–12s per line with reasoning on.

The rationales now quote the line. The DSB one reads:

> *"The item description 'Commute20' strongly suggests a cost related to travel
> to and from work, which is best categorized under Ground Transport (rail, bus,
> taxi, etc.) rather than airfare or lodging."*

## Four findings that change what comes next

### 1. Two of the four remaining declines are document-extraction defects, not categorizer defects

- The Aquatuning line has **no `item_name` at all**. Nothing was sent because
  nothing was stored.
- `Antal Produkt` is Danish for *"Quantity / Product"* — a **table header** the
  document extractor turned into a line item, on a 58,00 kr DSB receipt.

No prompt fixes either. They belong to `ai_api/documents/`, and the second one is
the same class of bug as the summary-row filter already in `vision.py`.

### 2. Temperature 0 is not determinism

`1 Voksen` — a DSB adult ticket — came back **Utilities (0.7)** on the first run
and **Ground Transport (0.9)** on the second. Identical line, identical prompt,
`VLLM_TEMPERATURE=0.0`. Continuous batching on vLLM does not give bit-identical
logits, and a thin line sits close enough to the decision boundary for that to
flip the answer.

This is the strongest argument yet for phase 2 as designed: a forced answer on a
thin line is partly a coin toss, so the confidence and the review queue are not
polish — they are what makes forcing an answer survivable. It also says the
confidence is doing real work: the wrong answer came back at **0.7** and the right
one at **0.9**.

### 3. Supplier enrichment would have decided `1 Voksen` outright

The run that got it right reasoned *"DSB is a public transport provider
(trains/buses)"* — knowledge it happened to have. The run that got it wrong did
not reach for it. A stored `Vendor.description` makes that a stated fact rather
than a coin toss, on every run. All 47 vendors currently have none.

### 4. The customer had already built the categories phase 4 proposes

Their tree is a `default_template` copy at `template_version: 1`, **38 nodes, 26
leaves** — eight leaves more than the template ships. What they added by hand:

| | code |
| --- | --- |
| `Travel & Entertainment > Ground Transport` | 6830 |
| `Financial Services > Banking & Account Fees` | 7300 |
| `Financial Services > Payment Processing Fees` | 7310 |
| `Financial Services > Levies & Royalties` | 7320 |
| `Insurance > Liability Insurance` | 7200 |
| `Insurance > Employee & Work Accident Insurance` | 7210 |
| `Insurance > Insurance Levies & Contributions` | 7220 |

Independent confirmation of task 4.1, arrived at without seeing the proposal —
and the codes and names to use, so the template matches what a real customer
converged on rather than what we guessed. Note they did **not** add
subscriptions/memberships; that leaf stays proposed but unevidenced.

It also confirms the copy semantics work as designed: their edits are theirs, and
a template bump must not reach into them.

## What this does not show

Nothing here measures the 31 lines that were already `ai_categorized` — those were
categorized under the old blind prompt and are untouched. Whether their categories
are right is a separate question, and re-running them would destroy the only
before-state we have. It is the right thing to do *after* phase 2, through
`POST /companies/{id}/recategorize`, with this file as the baseline.
