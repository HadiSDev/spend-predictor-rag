# CLAUDE.md - Project Overview & Guidelines

## Project

Autonomous invoice processing & spend categorization. A CrewAI `Flow` runs five
`Agent.kickoff()` stages (extract -> verify -> research_products -> categorize ->
ledger) per PDF invoice. Categorization is hierarchical and buyer-aware: L1
Direct/Indirect is derived from buyer context (buyer name + website scraped once
per run); L2/L3/leaf accounts come from a RAG-backed ChromaDB index of the chart
of accounts. Line items are web-searched (DuckDuckGo, no key) for product context
before categorization. Results are written to `output/ledger.csv`.

## Environment

- Managed with Astral `uv`; **Python 3.12** (ChromaDB's Pydantic-V1 internals
  break on 3.14).
- Install: `uv sync`
- Run: `uv run main.py`
- Test: `uv run pytest`

## Model Hosting

- Local vLLM, OpenAI-compatible at `http://localhost:8000/v1`, model
  `google/gemma-4-E4B-it` (CrewAI references it as `hosted_vllm/google/gemma-4-E4B-it`).
  Configured via `.env` (see `.env.example`).

## Layout

- `src/spend_predictor/` — package (config, models, pdf_loader, ledger, agents,
  grounding, web_context, flow, rag/)
- `data/` - chart of accounts + input invoices
- `output/ledger.csv` - generated results
