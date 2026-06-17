# Synthetic Invoice Generator + ANLS Benchmark — Design (Phase 1)

**Date:** 2026-06-13
**Status:** Approved (design); pending spec review before planning.

## Goal

Build a self-hosted, open-source generator that emits **labeled synthetic invoice
fixtures** — `(invoice PDF + structured fields + ERP journal entries + category
labels)` — and a **minimal scorer** that runs the existing extraction +
categorization pipeline over those fixtures and reports accuracy. The purpose is
to **benchmark the spend-categorization pipeline at scale** (extraction fidelity
and the Direct/Indirect + account categorization, including the run-to-run
categorization variance observed in live runs).

Phase 1 covers **invoices only**. Supermarket receipts (image + crumpling + OCR)
are **Phase 2** (documented at the end; not built now).

## Decisions (from brainstorming)

1. **Content engine:** LLM-enriched using the **local vLLM** model. Labels are
   chosen programmatically; the LLM only writes realistic surface text.
2. **Scope:** generator **plus** a minimal benchmark scorer.
3. **Renderer:** **WeasyPrint** (HTML/CSS → PDF) for high-quality, varied invoice
   layouts. Output is a clean text-layer PDF readable by the existing
   `pdfplumber` loader.
4. **Phasing:** invoices first (Phase 1); receipts + Augraphy + OCR are Phase 2.
5. **Generation engine:** **Bespoke Curator** for bulk inference (disk-cached,
   resumable, retries, parallelism) over the local vLLM, configured to return
   **free-text JSON parsed by `parsing.py`** — NOT Curator's guided/structured
   output. This deliberately avoids vLLM guided decoding, whose concurrent
   runaway was removed earlier in the project (see
   `avoid-vllm-guided-decoding`).
6. **ERP:** hand-rolled minimal double-entry (no `pyluca`/`beancount` dependency).
7. **Scoring metric:** **ANLS** (Average Normalized Levenshtein Similarity) via
   `shunk031/ANLS` for OCR/format-tolerant per-field extraction scoring, plus
   exact-match accuracy for the category labels.

## Core principle: ground-truth by construction

The pipeline under test must be scored against labels it cannot have influenced.
So the generator **chooses the labels first** (buyer, chart account, VAT regime,
amounts) as a plain-data `InvoicePlan`, then the LLM writes only the vendor name
and line-item descriptions *around* those fixed labels. The LLM never selects the
account or the Direct/Indirect class. Every fixture's labels are therefore correct
by construction — no post-hoc annotation step.

## Architecture — new subpackage `src/spend_predictor/synthdata/`

### `profiles.py` — buyer profiles
A small set of buyer profiles, each: `name`, `website`, `country_code`,
`vat_number`, `business_description`, and a **rule mapping chart accounts (or
level2 groups) to Direct vs Indirect**. This makes `level1` both ground-truth and
buyer-dependent (the same account can be Direct for one buyer, Indirect for
another). Example: a cloud-SaaS buyer treats `6010 Cloud Hosting` as **Direct**
(cost of revenue); a law firm treats it as **Indirect** (overhead).

### `sampler.py` — plan sampler (no LLM)
A seeded RNG produces an `InvoicePlan` dataclass:
- pick a buyer profile;
- pick **exactly one** chart-of-accounts leaf — the single **category label** for
  the invoice. All line items belong to that one account, so the ground-truth
  category is unambiguous and matches the pipeline's one-account-per-invoice
  output. (Multi-account invoices are a later enhancement, out of scope here.)
- pick a VAT regime: **EU (with `supplier`/`buyer` country codes + VAT numbers +
  per-line VAT)** or **US (no VAT)**;
- pick currency, line count, quantities, unit types, unit prices, and derive
  amounts/subtotal/tax/total so the arithmetic reconciles.
Deterministic: same seed → same set of plans. This is the source of all labels.

### `content.py` — LLM enrichment (Curator over local vLLM)
Given an `InvoicePlan`, generate realistic **vendor name** and **line-item
descriptions** consistent with the chosen account (optionally deliberately
cryptic, to stress the categorizer). Uses Curator for bulk/cached/parallel
inference but returns **free-text JSON** parsed via `parsing.py`
(`json_format_hint` + `parse_model`); no guided decoding. The enricher may only
fill descriptive text — it must not alter any labeled/numeric field.

### `erp.py` — double-entry journal
From the finished invoice build a balanced journal:
- **Dr** `<expense account_code>` = net (subtotal),
- **Dr** `VAT input` = tax (only if VAT present),
- **Cr** `Accounts Payable` = total.
Invariant: total debits == total credits. ~20 lines, no external dependency.

### `render/` — WeasyPrint templates
Several Jinja2 HTML/CSS invoice templates (distinct vendor looks) plus a renderer
that takes the assembled invoice record and writes a **text-layer PDF**. WeasyPrint
needs system libraries (Pango/cairo/GDK) — a one-time apt step, documented in the
README.

### `generate.py` — orchestrator + CLI
Pipeline: `plan → enrich → assemble & validate (models.ExtractedInvoice) →
render PDF → build ERP → write fixture bundle`. CLI:
`python -m spend_predictor.synthdata.generate --n 100 --seed 7 --out data/synthetic`.

## Fixture bundle (on disk)

Per invoice, `data/synthetic/<id>/`:
- `invoice.pdf` — the rendered document.
- `labels.json` — full ground-truth: the `ExtractedInvoice` field values + the
  category `{account_code, account_name, level1, level2, level3}` + buyer
  identity + the journal entries.

Plus a top-level `data/synthetic/manifest.jsonl` indexing every fixture (id, path,
buyer, account_code, vat_regime). The structured ground-truth reuses the existing
`models.py` schema as the single source of truth.

## Scorer — `score.py` (CLI: `python -m spend_predictor.synthdata.score --fixtures data/synthetic`)

Runs the **existing** pipeline (extract → categorize) over each `invoice.pdf` and
compares to `labels.json`:
- **Extraction fidelity:** per-field **ANLS** (`from anls import anls_score`),
  averaged per field and overall. ANLS tolerates minor OCR/formatting differences.
  Field-type handling: **string** fields (vendor, invoice number, country codes,
  VAT numbers, currency) scored directly with ANLS; **numeric** fields (subtotal,
  tax, total, amounts) scored by exact/near-equal match (small epsilon) rather
  than ANLS; **line items** scored by item-count match plus best-match alignment
  of predicted↔gold descriptions (ANLS on description, exact/near on amount).
- **Categorization accuracy:** exact `account_code` match rate; `level1`
  (Direct/Indirect) accuracy; `level2`/`level3` accuracy.
- **Output:** a printed summary (per-field ANLS table + category accuracy) and a
  per-fixture results CSV for drill-down.

## Data flow

```
seed ─▶ sampler.InvoicePlan (labels) ─▶ content.enrich (LLM surface text)
     ─▶ assemble + validate (ExtractedInvoice) ─▶ render (WeasyPrint PDF)
     ─▶ erp.journal ─▶ write bundle (invoice.pdf + labels.json) ─▶ manifest
scorer: for each bundle ─▶ run pipeline on invoice.pdf ─▶ compare to labels.json
     ─▶ ANLS (fields) + accuracy (category) ─▶ report
```

## Dependencies (Phase 1)

- `weasyprint` — HTML/CSS → PDF (system libs: Pango/cairo/GDK; document apt step).
- `faker` — cheap non-LLM scaffolding (addresses, dates, invoice numbers, VAT-number
  formats) so the LLM only handles parts that need realism.
- `bespokelabs-curator` — bulk inference (cached/resumable/parallel) over local vLLM.
- `anls` (`shunk031/ANLS`) — ANLS scoring.
- `reportlab` — retained for the existing `scripts/generate_sample_invoice.py`.

## Error handling

- Generation is best-effort per item: a failed enrichment or render logs and skips
  that fixture (does not abort the batch); the manifest records only written
  bundles. Curator's disk cache makes re-runs resume cheaply.
- The assembled record is validated against `models.ExtractedInvoice` before
  rendering; a validation failure skips the item with a logged reason.
- The scorer treats a pipeline error on a fixture as a zero-score row (recorded),
  not a crash.

## Testing (all offline; LLM + network stubbed via dependency injection)

- **sampler:** same seed → identical plans; arithmetic reconciles
  (lines→subtotal, subtotal+tax→total); EU plans carry country/VAT, US plans don't.
- **profiles/labels:** `level1` equals the buyer-profile rule for the chosen
  account (integrity).
- **erp:** debits == credits for VAT and non-VAT invoices.
- **render:** a rendered PDF's `pdfplumber` text contains the key fields
  (vendor, total, an invoice number).
- **scorer:** ANLS computation on known prediction/gold pairs; category accuracy
  on a constructed mix; per-fixture error path yields a zero row, not a crash.
- **bundle/manifest:** bundle writes and round-trips; manifest lists every bundle.

## Out of scope (Phase 1)

- No changes to the runtime extraction/categorization pipeline (the scorer
  consumes it as-is).
- No image output, no OCR, no Augraphy.

## Phase 2 (documented; not built now)

Supermarket **receipts**:
- thermal-style Jinja2 templates → rasterize;
- **Augraphy** augmentation applied **stochastically** — a random subset of
  receipts at varying intensity (folds/creases/lighting/fading), leaving some
  clean — to produce a realistic degradation distribution;
- output **images** (no text layer), so add an **OCR loader** to the pipeline;
- extend the scorer to consume image fixtures and measure OCR-path robustness
  across degradation levels.
