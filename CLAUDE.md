# CLAUDE.md - Project Overview & Guidelines

## Project

Autonomous invoice processing & spend categorization. A CrewAI `Flow` runs three
`Agent.kickoff()` stages (extract -> verify -> categorize) per PDF invoice;
categorization is RAG-backed over a ChromaDB index of the chart of accounts.
Results are written to `output/ledger.csv`.

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

- `src/spend_predictor/` - package (config, models, pdf_loader, ledger, agents,
  flow, rag/)
- `data/` - chart of accounts + input invoices
- `output/ledger.csv` - generated results
