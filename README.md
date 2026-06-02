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

## Setup

```bash
uv sync
cp .env.example .env   # then edit if your vLLM endpoint differs
```

The LLM is a local vLLM server exposing an OpenAI-compatible API at
`http://localhost:8000/v1` serving `google/gemma-4-E4B-it` (referenced as
`hosted_vllm/google/gemma-4-E4B-it`). Embeddings use a local
`sentence-transformers` model (`all-MiniLM-L6-v2`, downloaded on first run).

## Run

```bash
# Drop PDF invoices into data/invoices/ (a sample is included), then:
uv run main.py
```

Results are appended to `output/ledger.csv`. Skipped (unreadable/empty) invoices
are recorded with `status=skipped` and a reason.

## Test

```bash
uv run pytest
```

Unit tests run offline (no LLM, no model download - embeddings are faked).

## Configuration

Set the buyer in `.env` (`BUYER_NAME`, `BUYER_WEBSITE`) — the buyer's website is
scraped once per run to judge Direct/Indirect. Line items are web-searched
(DuckDuckGo, no key) to clarify products. The chart of accounts
(`data/chart_of_accounts.csv`) provides `level2`/`level3` and the leaf account;
Direct/Indirect is derived per invoice from the buyer context, not stored in the
chart. Replace the sample chart with your real one (same columns); the ChromaDB
index rebuilds when the row count changes.
