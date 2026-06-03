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

Each invoice produces exactly one ledger row. Columns include `buyer_name`,
`level1` (Direct/Indirect), `level2`, `level3`, `account_code`, `account_name`,
`total`, `arithmetic_ok`, `confidence`, and `notes`. Status is `processed`,
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
