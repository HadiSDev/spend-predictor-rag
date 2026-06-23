# Autonomous Invoice Processing & Spend Categorization (CrewAI + RAG)

A multi-agent pipeline that reads PDF invoices and codes each to a corporate
chart of accounts, writing results to a CSV ledger. Built on CrewAI (`Flow` +
`Agent.kickoff`) with RAG-backed categorization over a persisted ChromaDB index.

## Pipeline

```text
PDF -> extract -> verify -> research products -> categorize (leaf + Direct/Indirect) -> output/ledger.csv
```

1. **Extract** structured fields from the invoice text.
2. **Verify** the arithmetic (line items -> subtotal -> total).
3. **Categorize** picks the leaf account (L2/L3/leaf from the chart of accounts)
   and classifies Direct/Indirect from buyer and product context using RAG retrieval.

## Prerequisites

- [Astral `uv`](https://docs.astral.sh/uv/) and **Python 3.12** (uv installs it).
- A **local vLLM server** running and serving the model on an OpenAI-compatible
  API at `http://localhost:8000/v1` (model `google/gemma-4-E4B-it`, referenced by
  CrewAI as `hosted_vllm/google/gemma-4-E4B-it`). Confirm it's up with
  `curl -s http://localhost:8000/v1/models`.
- **Internet access** at run time — the buyer's website is scraped and each line
  item is web-searched (both degrade gracefully if offline).
- Embeddings use a local `sentence-transformers` model (`all-MiniLM-L6-v2`,
  downloaded automatically on first run).

## Setup

```bash
# 1. Install dependencies (creates the .venv on Python 3.12)
uv sync

# 2. Create your env file and set the BUYER (this drives Direct/Indirect)
cp .env.example .env
#    then edit .env and set at least:
#      BUYER_NAME=Your Company, Inc.
#      BUYER_WEBSITE=https://yourcompany.example
#    (VLLM_* defaults already point at http://localhost:8000/v1)
```

## Run

```bash
# 1. Drop PDF invoices into data/invoices/ (a sample is included).

# 2. Make sure your vLLM server is running (see Prerequisites).

# 3. Run the pipeline:
uv run main.py

# 4. Inspect the results:
cat output/ledger.csv
```

Each invoice produces exactly one ledger row. Columns include `vendor_name`,
`supplier_country_code`, `supplier_vat_number`, `buyer_name`, `buyer_country_code`,
`buyer_vat_number`, `level1` (Direct/Indirect), `level2`, `level3`, `account_code`,
`account_name`, `total`, `arithmetic_ok`, `confidence`, and `notes`. Status is `processed`,
`skipped` (unreadable/empty PDF), or `error` (a stage failed, e.g. an LLM
timeout) — skipped/error rows record the reason in `notes` and the batch
continues.

> **First run is slower:** it scrapes the buyer site and searches each line item;
> both are cached under `data/web_cache/` (gitignored), so re-runs are faster.

Invoices are independent and processed **concurrently** — set `INVOICE_CONCURRENCY`
in `.env` (default `4`) to match what your vLLM server handles; `1` forces strictly
sequential processing (deterministic ledger order). The shared index build and
buyer-website scrape happen once, before the batch.

### Changing the chart of accounts

`data/chart_of_accounts.csv` provides `level2`/`level3` and the leaf account
(`account_code`, `account_name`). Direct/Indirect (`level1`) is **not** stored
here — it's judged per invoice from the buyer context. Replace the sample with
your real chart (same columns). The ChromaDB index rebuilds automatically when
the **row count** changes; if you edit rows without changing the count, force a
rebuild:

```bash
rm -rf chroma_db
```

## Test

```bash
uv run pytest
```

Unit tests run fully offline (no LLM, no network, no model download — web lookups
and embeddings are faked via dependency injection).

## Synthetic data & benchmarking

The `spend_predictor.synthdata` subpackage generates labeled synthetic invoice
fixtures (PDF + structured fields + ERP journal entries + category labels) and
benchmarks the extraction/categorization pipeline against them using ANLS. Labels
are chosen programmatically from the chart of accounts and buyer profiles
(Direct/Indirect is derived from the buyer's business), so every fixture's labels
are ground-truth by construction.

**By default, the generator produces richly varied data with no LLM required:**
industry-flavored vendor names, per-account realistic line-item catalogs, 9 distinct
invoice templates (modern, classic, minimal, corporate, eu_vat, us_net30, freelancer,
saas_receipt, utility) chosen at random, plus per-invoice randomized accent color,
font, logo/monogram, and realistic extra fields (addresses, PO number, payment terms,
due date, bank/IBAN, notes). The `--live` flag (which requires `uv sync --group live`
+ a running vLLM) is optional — it only swaps in LLM-written line-item descriptions
for extra realism; all other variation and quality work without it. Templates are
auto-discovered from `src/spend_predictor/synthdata/render/templates/*.html`, so you
can drop in your own `.html` template and it joins the rotation automatically.

### Installation

Scoring and the unit tests do NOT need the `live` group. PDF rendering uses
WeasyPrint (a regular project dependency); it needs system libraries that are
usually already present on desktop Linux, but on a bare system install them with:

```bash
sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev libcairo2
```

To use LLM-generated line-item descriptions, install the optional dependency group:

```bash
uv sync --group live
```

### Generate synthetic invoices

```bash
uv run python -m spend_predictor.synthdata.generate --n 100 --seed 7 --out data/synthetic
```

**Requires:** by default, NO LLM or vLLM — the generator produces richly varied
invoices deterministically. To use LLM-written line-item descriptions, pass
`--live` (which requires `uv sync --group live` + a running vLLM server). The
`--cryptic` flag (terse, harder-to-categorize descriptions) only has an effect
with `--live`.

Each fixture is written to its own directory:
- `data/synthetic/<id>/invoice.pdf` — the rendered invoice
- `data/synthetic/<id>/labels.json` — ground-truth: the extracted fields, the
  category (`account_code`, `level1`/`level2`/`level3`), the buyer, and the
  double-entry journal
- `data/synthetic/manifest.jsonl` — an index of all generated fixtures

### Author new templates from web references (optional)

Grow the template library by drafting new templates from real invoice *designs*
found online. This is an offline developer tool — separate from the generator —
and is **human-gated**: it stages drafts for you to review, and never writes into
`render/templates/` itself.

```bash
uv run python -m spend_predictor.synthdata.templategen --n 5
# or drive the search yourself:
uv run python -m spend_predictor.synthdata.templategen --query "eu vat invoice template" --n 8
```

It searches DuckDuckGo images (no key), drafts a Jinja2 template per image via the
local **vision** LLM (requires your vLLM server to serve the model with vision
enabled), then validates each draft — it must render cleanly, contain the required
placeholders, and pass a **no-real-data lint** (no emails, long digit runs, or
embedded image URLs). Results land in `data/template_drafts/` (gitignored):
passing drafts as `<name>.html` + `<name>.pdf` preview, failures under
`_rejected/` with a reason, plus a `report.md`. Review them, then move the good
`.html` files into `src/spend_predictor/synthdata/render/templates/` — the
generator auto-discovers them.

**No real data ever enters a template:** the vision model is instructed to copy
only layout/styling and use Jinja placeholders for all data; the lint and your
manual review are the backstops.

### Score extraction & categorization accuracy

```bash
uv run python -m spend_predictor.synthdata.score --fixtures data/synthetic
```

**Requires:** the local vLLM server running — scoring runs the real
extract → categorize pipeline (which calls the model) over each fixture PDF and
compares the result to `labels.json`. It reports per-field ANLS for extraction
plus exact-match accuracy for the leaf account code and the Direct/Indirect (L1),
L2, and L3 labels.

### Output

The `data/synthetic/` directory is gitignored — it is regenerated per run and not
committed.
