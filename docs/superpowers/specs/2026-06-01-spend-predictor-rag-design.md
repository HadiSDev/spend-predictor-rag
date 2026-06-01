# Spend Predictor RAG — Design

**Date:** 2026-06-01
**Status:** Approved (pending written-spec review)

## 1. Purpose

An autonomous invoice-processing pipeline that takes a PDF invoice and produces a
spend categorization coded to a corporate chart of accounts. It replaces fragile
regex parsing with a multi-agent assembly line and uses RAG over the chart of
accounts so the categorization agent picks from a constrained, relevant set of
accounts rather than free-associating (which invites hallucination).

End-to-end flow:

```
PDF in data/invoices/  →  extract text  →  [extract → verify → categorize]  →  append row to output/ledger.csv
```

## 2. Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Categorization | RAG / vector retrieval over chart of accounts | Matches repo intent (`-rag`); constrains the agent to relevant accounts |
| Input format | PDF files | Parsed with `pdfplumber` |
| LLM | Local vLLM, OpenAI-compatible at `http://localhost:8000/v1`, model `hosted_vllm/google/gemma-4-E4B-it` | Per project guidelines; configurable via `.env`. CrewAI 1.x ships native providers without litellm, so the vLLM endpoint uses the `hosted_vllm/` prefix (the `openai/` prefix rejects non-OpenAI model names) |
| Embeddings | Local `sentence-transformers` (`all-MiniLM-L6-v2`) | No extra server, CPU-friendly; Gemma is generative, not an embedding model |
| Vector store | ChromaDB, persisted to disk | Embed the chart once, reuse across runs |
| Output | CSV ledger (`output/ledger.csv`) | Accounting-friendly, inspectable |
| Chart of accounts | Generated sample CSV | Placeholder the user can replace with the real chart |
| Framework | CrewAI `Flow` with three `Agent.kickoff()` steps | Flow as the foundation, `Agent.kickoff()` (not a Crew) for distinct-agent-per-step linear pipelines |
| Package mgmt | `uv` (existing `uv init` scaffold) | Repo already initialized with uv; we add `src/spend_predictor/` modules by hand (no `@CrewBase`/YAML needed for the `Agent.kickoff` design) |
| Python version | 3.12 (`>=3.12,<3.13`) | ChromaDB relies on Pydantic V1 internals that break on 3.14; 3.12 is the tested CrewAI+ChromaDB combo and matches CLAUDE.md |
| Entry point | `uv run main.py` | Root `main.py` runs the flow over `data/invoices/` (matches README) |

## 3. Architecture

### 3.1 Scaffolding

The repo is already initialized with `uv init` (`pyproject.toml`, `uv.lock`, a
placeholder root `main.py`, `crewai` installed, `CLAUDE.md` at root). We build on
that scaffold rather than re-running `crewai create flow`: the `Agent.kickoff()`
design needs no `@CrewBase`/YAML, so the project is plain Python modules under a
new `src/spend_predictor/` package (`uv` uses a src layout). First, the Python
version is repinned from 3.14 to **3.12** (see §2) and the venv recreated.

### 3.2 Project structure (target)

```
spend-predictor-rag/
├── main.py                     # entry: runs InvoiceFlow over data/invoices/ (uv run main.py)
├── pyproject.toml              # uv; requires-python >=3.12,<3.13; deps added
├── .env / .env.example         # vLLM base URL, model, embedding model
├── .gitignore                  # adds chroma_db/, output/, .env
├── CLAUDE.md                   # run cmds updated (uv run main.py)
├── README.md                   # run cmds updated (uv sync / uv run main.py)
├── data/
│   ├── chart_of_accounts.csv   # sample: account_code, account_name, description, category
│   └── invoices/               # drop PDFs here; one sample invoice included
├── output/
│   └── ledger.csv              # generated (header written on first run)
├── chroma_db/                  # persisted RAG index (gitignored)
└── src/spend_predictor/
    ├── __init__.py
    ├── flow.py                 # InvoiceFlow + run_all() (loops over PDFs)
    ├── config.py               # env loading + CrewAI LLM factory
    ├── models.py               # Pydantic schemas (§3.4)
    ├── agents.py               # factory funcs: make_extractor/verifier/categorizer Agents
    ├── grounding.py            # validate-and-snap categorization guardrail
    ├── pdf_loader.py           # pdfplumber → text
    ├── ledger.py               # CSV append (header-aware)
    └── rag/
        ├── __init__.py
        └── indexer.py          # build/load Chroma index; retrieve_accounts/load_accounts
```

> Note: the root `main.py` is a thin entry that calls `run_all()` in
> `spend_predictor.flow`, so `uv run main.py` works (matches the README). The
> package uses a `src/` layout, so `pyproject.toml` declares
> `[tool.hatchling]`/packages accordingly (or the uv default build backend).

### 3.3 The Flow (`src/spend_predictor/flow.py`)

`InvoiceFlow(Flow[InvoiceState])` processes **one** invoice with structured
state. Each reasoning stage is its own `@listen` step running an
`Agent.kickoff(..., response_format=Model)`:

- `@start load_invoice` — read `state.pdf_path`, extract text via `pdf_loader`.
  On empty/failed extraction, mark `state.skipped = True` with a reason.
- `@listen(load_invoice) extract` — if not skipped, run the extractor agent
  (`response_format=ExtractedInvoice`) over `state.invoice_text`; store
  `result.pydantic` in `state.extracted`.
- `@listen(extract) verify` — if not skipped, run the verifier agent
  (`response_format=VerificationResult`) over `state.extracted`; store in
  `state.verification`.
- `@listen(verify) categorize` — if not skipped, run the categorizer agent
  (has the RAG tool, `response_format=CategorizedInvoice`); store in
  `state.categorized`.
- `@listen(categorize) record_to_ledger` — append a row to the CSV ledger.
  Skipped invoices still get a row, with `status=skipped` and the reason recorded
  in the `notes` column (see §3.6).

Each post-load step early-returns when `state.skipped` is set, so a skip
propagates cleanly to `record_to_ledger`.

`InvoiceState` (Pydantic) fields: `pdf_path`, `invoice_text`, `skipped`,
`skip_reason`, `errored`, `error_reason`, `extracted`, `verification`,
`categorized`, `categorization_note`.

`run_all()` (called by the root `main.py`, i.e. `uv run main.py`) lists every
`*.pdf` in `data/invoices/`, ensures the Chroma index exists (build once if
missing), and runs `InvoiceFlow().kickoff(inputs={"pdf_path": p})` for each,
printing a per-invoice summary.

### 3.4 Data models (`models.py`)

```python
class LineItem(BaseModel):
    description: str
    quantity: float | None
    unit_price: float | None
    amount: float

class ExtractedInvoice(BaseModel):
    vendor_name: str
    invoice_number: str | None
    invoice_date: str | None          # ISO if parseable, else raw
    currency: str | None
    line_items: list[LineItem]
    subtotal: float | None
    tax: float | None
    total: float

class VerificationResult(BaseModel):
    arithmetic_ok: bool
    discrepancies: list[str]
    notes: str | None

class CategorizedInvoice(BaseModel):
    account_code: str
    account_name: str
    category: str
    confidence: float                  # 0..1
    rationale: str
```

Each agent is called with `response_format` set to the matching model, so CrewAI
enforces and retries on schema mismatch. Structured outputs are read via
`result.pydantic`.

### 3.5 The reasoning agents (`agents.py`)

Three factory functions, each returning a purpose-built `Agent` (specific
role / goal / backstory per the design-agent skill). All share the vLLM `LLM`
from `config.get_llm()`. They are invoked via `Agent.kickoff()` from the Flow
steps in §3.3 — no Crew layer, since the pipeline is linear and each step is a
distinct agent with its own persona, output schema, and tool surface.

- **make_extractor()** → no tools. Step prompt passes `state.invoice_text`;
  returns `ExtractedInvoice`. Pulls structured fields from raw invoice text.
- **make_verifier()** → no tools. Step prompt passes the extracted invoice;
  returns `VerificationResult`. Recomputes that line items sum to subtotal and
  subtotal + tax ≈ total (small float tolerance); lists discrepancies. Flags but
  never blocks.
- **make_categorizer()** → **no tools** (deterministic retrieval, see below).
  Step prompt passes the invoice query plus the top-K candidate accounts that the
  flow retrieved in code; the agent returns `CategorizedInvoice`, choosing from
  the injected candidates. Then the flow's grounding guardrail (§3.6) validates
  the chosen code.

> **Design evolution (from live testing).** The categorizer originally used an
> agentic `ChartOfAccountsSearchTool` (LLM tool-calling). Live runs against the
> local vLLM + small Gemma model showed two problems: (1) tool-calling needs the
> server started with `--enable-auto-tool-choice` and is slow/unstable (a
> multi-iteration loop per invoice), and (2) the model fabricated account codes
> even when the tool returned the right ones. We switched to **deterministic
> retrieval**: the flow fetches candidates in code and the toolless categorizer
> makes one fast structured pick, validated by a grounding guardrail. The
> `ChartOfAccountsSearchTool` was removed.

### 3.6 RAG layer (`rag/`) and grounding guardrail

- `indexer.py`:
  - `build_index()` — read `data/chart_of_accounts.csv`, embed each account
    (`"{account_name}: {description} (category)"`) with `all-MiniLM-L6-v2`, and
    upsert into a persisted Chroma collection in `chroma_db/`. Idempotent: if the
    collection already has the expected count, skip rebuild.
  - `get_collection()` — open the persisted collection.
  - `retrieve_accounts(query, top_k=5)` — embed the query and return the top-K
    chart-of-accounts rows (metadata dicts), best-first. Used by the categorize
    step for both the candidate shortlist and the grounding fallback.
  - `load_accounts()` — return the full chart of accounts as row dicts (for
    validating that a chosen code is genuine).
- `grounding.py`:
  - `ground_categorization(categorized, candidates, accounts_by_code)` — if the
    model's `account_code` is a real chart account, keep it and canonicalize the
    name/category from the chart; otherwise snap to the top retrieved candidate
    and return a note describing the correction. Guarantees every processed row
    carries a real account code regardless of model behavior.

### 3.7 Configuration (`config.py`)

Reads `.env`:
- `VLLM_BASE_URL` (default `http://localhost:8000/v1`)
- `VLLM_MODEL` (default `hosted_vllm/google/gemma-4-E4B-it`)
- `VLLM_API_KEY` (default dummy, vLLM ignores it)
- `VLLM_MAX_TOKENS` (default `8192`) and `VLLM_TIMEOUT` (default `120`s) — bound
  each LLM call. Without `max_tokens`, a structured-output request can run toward
  the model's full context window and hang the pipeline (observed in the live
  smoke test); the timeout fails a stalled request instead of blocking forever.
- `EMBEDDING_MODEL` (default `all-MiniLM-L6-v2`)
- `CHART_OF_ACCOUNTS_PATH`, `INVOICES_DIR`, `LEDGER_PATH`, `CHROMA_DIR`

`get_llm()` returns a CrewAI `LLM(model=..., base_url=..., api_key=..., max_tokens=..., timeout=...)`.

### 3.8 Ledger (`ledger.py`)

`append_row(result)` writes to `output/ledger.csv`, creating the file with a
header if absent. Columns:

```
source_file, status, invoice_date, vendor_name, invoice_number, total, currency,
account_code, account_name, category, arithmetic_ok, confidence, notes
```

`status` is `processed`, `skipped`, or `error`. For skipped/error invoices, all
categorization fields are blank and `notes` holds the reason. For processed
invoices, `notes` carries any verification discrepancies and/or a grounding note
(when a hallucinated code was snapped to a real account).

## 4. Error Handling

- **Unreadable / empty PDF** → flow marks `skipped`, logs a warning, continues to
  the next file. A `status=skipped` row is written to the ledger with the reason
  in `notes` (no fabricated categorization values).
- **A reasoning stage fails** (LLM timeout, connection error, unparseable
  structured output after retries) → the flow records `status=error` with the
  reason (e.g. "verify failed: Request timed out") and the batch continues to the
  next invoice. Every invoice therefore produces exactly one ledger row.
- **Structured-output mismatch** → CrewAI retries against the Pydantic schema;
  if it still fails, the stage errors as above.
- **Fabricated account code** → the grounding guardrail snaps to the top
  retrieved candidate and notes the correction; the row is still written.
- **Verification discrepancies** → recorded (`arithmetic_ok=False`,
  `discrepancies` in `notes`), never fatal; the ledger row is still written.

## 5. Testing (TDD)

Unit tests (fast, no LLM):
- `pdf_loader` — extracts text from a generated sample PDF fixture; returns empty
  signal for a blank/garbage PDF.
- `rag` — `build_index` is idempotent; `search_tool` returns the expected
  account for an obvious query (e.g. "cloud hosting" → an IT/software account).
- `ledger` — writes header once, appends rows, round-trips values.

Live end-to-end smoke test (manual / requires vLLM):
- `uv run main.py` against the sample invoice produces a ledger row with a
  plausible account code.

A small test fixture PDF is generated (e.g. via `reportlab`) so `pdf_loader`
tests run without committing binary blobs, or a minimal sample invoice PDF is
committed under `data/invoices/`.

## 6. Out of Scope (YAGNI)

- Image/scanned-invoice OCR (PDF-text only for now; structure leaves room to add
  a vision/OCR step later).
- Multi-currency normalization / FX.
- A database backend or web UI.
- Authentication, multi-tenant, or batch scheduling.
