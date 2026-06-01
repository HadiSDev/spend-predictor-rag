# Spend Predictor RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an autonomous invoice-processing pipeline that takes PDF invoices and produces spend categorizations coded to a corporate chart of accounts, written to a CSV ledger.

**Architecture:** A CrewAI `Flow` processes one invoice per kickoff through five steps — load PDF text, then three `Agent.kickoff()` reasoning stages (extract → verify → categorize), then write a ledger row. Categorization is RAG-backed: a custom tool retrieves the most relevant accounts from a persisted ChromaDB index of the chart of accounts. A root `main.py` runs the flow over every PDF in `data/invoices/`.

**Tech Stack:** Python 3.12, uv, CrewAI (`Flow` + `Agent.kickoff`), Pydantic v2, pdfplumber, sentence-transformers (`all-MiniLM-L6-v2`), ChromaDB, local vLLM (OpenAI-compatible) serving `google/gemma-4-E4B-it`. Tests: pytest + reportlab.

**Spec:** `docs/superpowers/specs/2026-06-01-spend-predictor-rag-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `.python-version`, `pyproject.toml` | Pin Python 3.12, declare deps, src-layout build + pytest config |
| `main.py` (root) | Thin entry: `run_all()` over `data/invoices/` (`uv run main.py`) |
| `src/spend_predictor/__init__.py` | Package marker |
| `src/spend_predictor/config.py` | Env loading, paths, `get_llm()` LLM factory |
| `src/spend_predictor/models.py` | Pydantic schemas + `InvoiceState` |
| `src/spend_predictor/pdf_loader.py` | `extract_text(path)` via pdfplumber |
| `src/spend_predictor/ledger.py` | `build_ledger_row(...)`, `append_row(...)` CSV writer |
| `src/spend_predictor/rag/__init__.py` | Package marker |
| `src/spend_predictor/rag/indexer.py` | Embeddings, `build_index()`, `get_collection()` |
| `src/spend_predictor/rag/search_tool.py` | `ChartOfAccountsSearchTool` (CrewAI BaseTool) |
| `src/spend_predictor/agents.py` | `make_extractor/verifier/categorizer()` factories |
| `src/spend_predictor/flow.py` | `InvoiceFlow` + `run_all()` |
| `data/chart_of_accounts.csv` | Sample chart of accounts |
| `data/invoices/sample_invoice.pdf` | Generated sample invoice |
| `scripts/generate_sample_invoice.py` | Reproducibly regenerate the sample PDF |
| `tests/...` | One test module per source module |
| `.env.example`, `.gitignore` | Config template, ignores |

---

## Task 1: Project setup — Python 3.12, deps, src layout

**Files:**
- Modify: `.python-version`
- Modify: `pyproject.toml`
- Create: `src/spend_predictor/__init__.py`
- Create: `src/spend_predictor/rag/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Repin Python version**

Overwrite `.python-version` with exactly:

```
3.12
```

- [ ] **Step 2: Update `pyproject.toml`**

Replace the file with:

```toml
[project]
name = "spend-predictor-rag"
version = "0.1.0"
description = "Autonomous invoice processing & spend categorization with CrewAI + RAG"
readme = "README.md"
requires-python = ">=3.12,<3.13"
dependencies = [
    "crewai>=1.14.6",
    "pydantic>=2.12.5",
    "python-dotenv>=1.2.2",
    "pdfplumber>=0.11.0",
    "chromadb>=0.5.0",
    "sentence-transformers>=3.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "reportlab>=4.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/spend_predictor"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 3: Create package markers and test dirs**

Create empty `src/spend_predictor/__init__.py`, empty `src/spend_predictor/rag/__init__.py`, and empty `tests/__init__.py`.

- [ ] **Step 4: Write the smoke test**

Create `tests/test_smoke.py`:

```python
def test_package_imports():
    import spend_predictor

    assert spend_predictor is not None
```

- [ ] **Step 5: Sync the environment on Python 3.12**

Run: `uv sync`
Expected: uv resolves and installs on Python 3.12 (it may download a 3.12 toolchain). No ChromaDB Pydantic-V1 warning about Python 3.14.

- [ ] **Step 6: Run the smoke test**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS (1 passed).

- [ ] **Step 7: Commit**

```bash
git add .python-version pyproject.toml uv.lock src/ tests/ README.md CLAUDE.md main.py
git commit -m "chore: pin python 3.12, src layout, add deps and smoke test"
```

> Note: this commit also brings the previously-untracked uv scaffold (`README.md`, `CLAUDE.md`, `main.py`) under version control for the first time.

---

## Task 2: Config module

**Files:**
- Create: `src/spend_predictor/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from pathlib import Path

from spend_predictor import config


def test_default_paths_resolve_under_project_root():
    root = config.PROJECT_ROOT
    assert Path(config.CHART_OF_ACCOUNTS_PATH) == root / "data" / "chart_of_accounts.csv"
    assert Path(config.INVOICES_DIR) == root / "data" / "invoices"
    assert Path(config.LEDGER_PATH) == root / "output" / "ledger.csv"
    assert Path(config.CHROMA_DIR) == root / "chroma_db"


def test_get_llm_uses_vllm_settings():
    llm = config.get_llm()
    assert llm.model == config.VLLM_MODEL
    assert llm.base_url == config.VLLM_BASE_URL
    assert config.VLLM_MODEL == "openai/google/gemma-4-E4B-it"
    assert config.VLLM_BASE_URL == "http://localhost:8000/v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError`/`AttributeError` (config not implemented).

- [ ] **Step 3: Write the implementation**

Create `src/spend_predictor/config.py`:

```python
"""Environment configuration and the vLLM LLM factory."""
from __future__ import annotations

import os
from pathlib import Path

from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

# repo root = .../spend-predictor-rag (config.py is at src/spend_predictor/config.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "openai/google/gemma-4-E4B-it")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "not-needed")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

CHART_OF_ACCOUNTS_PATH = os.getenv(
    "CHART_OF_ACCOUNTS_PATH", str(PROJECT_ROOT / "data" / "chart_of_accounts.csv")
)
INVOICES_DIR = os.getenv("INVOICES_DIR", str(PROJECT_ROOT / "data" / "invoices"))
LEDGER_PATH = os.getenv("LEDGER_PATH", str(PROJECT_ROOT / "output" / "ledger.csv"))
CHROMA_DIR = os.getenv("CHROMA_DIR", str(PROJECT_ROOT / "chroma_db"))


def get_llm() -> LLM:
    """Return a CrewAI LLM pointed at the local vLLM OpenAI-compatible endpoint."""
    return LLM(model=VLLM_MODEL, base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 passed).

> If `llm.base_url` is not exposed as that attribute name by your CrewAI version, adjust the assertion to the actual attribute (e.g. inspect `vars(llm)`); the constructor call itself is correct.

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/config.py tests/test_config.py
git commit -m "feat: config module with paths and vLLM LLM factory"
```

---

## Task 3: Data models

**Files:**
- Create: `src/spend_predictor/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
from spend_predictor.models import (
    CategorizedInvoice,
    ExtractedInvoice,
    InvoiceState,
    LineItem,
    VerificationResult,
)


def test_extracted_invoice_roundtrip():
    inv = ExtractedInvoice(
        vendor_name="Acme Cloud",
        invoice_number="INV-1",
        invoice_date="2026-05-01",
        currency="USD",
        line_items=[LineItem(description="cloud hosting", quantity=1, unit_price=100.0, amount=100.0)],
        subtotal=100.0,
        tax=0.0,
        total=100.0,
    )
    assert inv.line_items[0].amount == 100.0
    assert inv.total == 100.0


def test_optional_fields_default_to_none():
    inv = ExtractedInvoice(vendor_name="X", line_items=[], total=0.0)
    assert inv.invoice_number is None
    assert inv.subtotal is None


def test_invoice_state_constructs_with_defaults():
    state = InvoiceState()
    assert state.pdf_path == ""
    assert state.skipped is False
    assert state.extracted is None


def test_verification_and_categorization_models():
    v = VerificationResult(arithmetic_ok=False, discrepancies=["total mismatch"], notes=None)
    c = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting", category="IT", confidence=0.9, rationale="ok"
    )
    assert v.discrepancies == ["total mismatch"]
    assert c.account_code == "6010"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `src/spend_predictor/models.py`:

```python
"""Pydantic data models for the invoice pipeline and flow state."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float


class ExtractedInvoice(BaseModel):
    vendor_name: str
    invoice_number: str | None = None
    invoice_date: str | None = None  # ISO if parseable, else raw
    currency: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float


class VerificationResult(BaseModel):
    arithmetic_ok: bool
    discrepancies: list[str] = Field(default_factory=list)
    notes: str | None = None


class CategorizedInvoice(BaseModel):
    account_code: str
    account_name: str
    category: str
    confidence: float  # 0..1
    rationale: str


class InvoiceState(BaseModel):
    """Flow state for processing a single invoice."""

    pdf_path: str = ""
    invoice_text: str = ""
    skipped: bool = False
    skip_reason: str = ""
    extracted: ExtractedInvoice | None = None
    verification: VerificationResult | None = None
    categorized: CategorizedInvoice | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/models.py tests/test_models.py
git commit -m "feat: pydantic models for invoice pipeline and flow state"
```

---

## Task 4: PDF loader

**Files:**
- Create: `src/spend_predictor/pdf_loader.py`
- Test: `tests/test_pdf_loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pdf_loader.py`:

```python
import pytest

from spend_predictor.pdf_loader import extract_text


def _make_pdf(path, lines):
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    y = 750
    for line in lines:
        c.drawString(100, y, line)
        y -= 20
    c.save()


def test_extract_text_returns_content(tmp_path):
    pdf = tmp_path / "inv.pdf"
    _make_pdf(pdf, ["INVOICE", "Acme Corp", "Total 123.45"])
    text = extract_text(pdf)
    assert "INVOICE" in text
    assert "Acme Corp" in text


def test_extract_text_empty_pdf_returns_empty(tmp_path):
    pdf = tmp_path / "blank.pdf"
    _make_pdf(pdf, [])
    assert extract_text(pdf).strip() == ""


def test_extract_text_raises_on_nonpdf(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_text("this is not a pdf")
    with pytest.raises(Exception):
        extract_text(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pdf_loader.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `src/spend_predictor/pdf_loader.py`:

```python
"""Extract plain text from a PDF invoice."""
from __future__ import annotations

from pathlib import Path

import pdfplumber


def extract_text(path: str | Path) -> str:
    """Return the concatenated text of all pages, stripped.

    Raises if the file cannot be opened/parsed as a PDF; returns "" for a
    valid PDF that contains no extractable text.
    """
    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
    return "\n".join(parts).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pdf_loader.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/pdf_loader.py tests/test_pdf_loader.py
git commit -m "feat: pdfplumber-based PDF text extraction"
```

---

## Task 5: Ledger writer

**Files:**
- Create: `src/spend_predictor/ledger.py`
- Test: `tests/test_ledger.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger.py`:

```python
import csv

from spend_predictor.ledger import LEDGER_COLUMNS, append_row, build_ledger_row
from spend_predictor.models import (
    CategorizedInvoice,
    ExtractedInvoice,
    LineItem,
    VerificationResult,
)


def _read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_append_writes_header_once_then_rows(tmp_path):
    ledger = tmp_path / "ledger.csv"
    append_row({"source_file": "a.pdf", "status": "processed"}, ledger)
    append_row({"source_file": "b.pdf", "status": "skipped"}, ledger)
    rows = _read(ledger)
    assert [r["source_file"] for r in rows] == ["a.pdf", "b.pdf"]
    # header written exactly once
    assert ledger.read_text().count(",".join(LEDGER_COLUMNS)) == 1


def test_build_ledger_row_processed():
    extracted = ExtractedInvoice(
        vendor_name="Acme Cloud",
        invoice_number="INV-1",
        invoice_date="2026-05-01",
        currency="USD",
        line_items=[LineItem(description="cloud hosting", amount=100.0)],
        subtotal=100.0,
        tax=0.0,
        total=100.0,
    )
    verification = VerificationResult(arithmetic_ok=True, discrepancies=[], notes=None)
    categorized = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting", category="IT", confidence=0.9, rationale="ok"
    )
    row = build_ledger_row(
        source_file="inv.pdf",
        skipped=False,
        skip_reason="",
        extracted=extracted,
        verification=verification,
        categorized=categorized,
    )
    assert row["status"] == "processed"
    assert row["vendor_name"] == "Acme Cloud"
    assert row["account_code"] == "6010"
    assert row["arithmetic_ok"] is True


def test_build_ledger_row_skipped_has_reason_and_blanks():
    row = build_ledger_row(
        source_file="bad.pdf",
        skipped=True,
        skip_reason="empty PDF text",
        extracted=None,
        verification=None,
        categorized=None,
    )
    assert row["status"] == "skipped"
    assert row["notes"] == "empty PDF text"
    assert row["account_code"] == ""
    assert row["vendor_name"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ledger.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `src/spend_predictor/ledger.py`:

```python
"""Append categorization results to the CSV ledger."""
from __future__ import annotations

import csv
from pathlib import Path

from .models import CategorizedInvoice, ExtractedInvoice, VerificationResult

LEDGER_COLUMNS = [
    "source_file",
    "status",
    "invoice_date",
    "vendor_name",
    "invoice_number",
    "total",
    "currency",
    "account_code",
    "account_name",
    "category",
    "arithmetic_ok",
    "confidence",
    "notes",
]


def build_ledger_row(
    *,
    source_file: str,
    skipped: bool,
    skip_reason: str,
    extracted: ExtractedInvoice | None,
    verification: VerificationResult | None,
    categorized: CategorizedInvoice | None,
) -> dict:
    """Build a ledger row dict from flow results."""
    if skipped:
        row = {col: "" for col in LEDGER_COLUMNS}
        row["source_file"] = source_file
        row["status"] = "skipped"
        row["notes"] = skip_reason
        return row

    if verification and verification.discrepancies:
        notes = "; ".join(verification.discrepancies)
    else:
        notes = (verification.notes if verification else "") or ""

    return {
        "source_file": source_file,
        "status": "processed",
        "invoice_date": (extracted.invoice_date if extracted else "") or "",
        "vendor_name": extracted.vendor_name if extracted else "",
        "invoice_number": (extracted.invoice_number if extracted else "") or "",
        "total": extracted.total if extracted else "",
        "currency": (extracted.currency if extracted else "") or "",
        "account_code": categorized.account_code if categorized else "",
        "account_name": categorized.account_name if categorized else "",
        "category": categorized.category if categorized else "",
        "arithmetic_ok": verification.arithmetic_ok if verification else "",
        "confidence": categorized.confidence if categorized else "",
        "notes": notes,
    }


def append_row(row: dict, path: str | Path) -> None:
    """Append a row to the ledger CSV, writing the header if the file is new."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in LEDGER_COLUMNS})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ledger.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/ledger.py tests/test_ledger.py
git commit -m "feat: CSV ledger writer with processed/skipped rows"
```

---

## Task 6: RAG indexer

**Files:**
- Create: `src/spend_predictor/rag/indexer.py`
- Test: `tests/test_indexer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_indexer.py`. The fake embedder makes a deterministic keyword vector so tests need no model download:

```python
import csv

from spend_predictor.rag import indexer

VOCAB = ["cloud", "office", "travel", "legal", "meal"]


def fake_embed(texts):
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


def _write_coa(path):
    rows = [
        {"account_code": "6010", "account_name": "Cloud Hosting", "description": "cloud servers and hosting", "category": "IT"},
        {"account_code": "6500", "account_name": "Office Supplies", "description": "office stationery", "category": "Admin"},
        {"account_code": "7000", "account_name": "Travel", "description": "travel and flights", "category": "Ops"},
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_code", "account_name", "description", "category"])
        w.writeheader()
        w.writerows(rows)


def test_build_index_populates_collection(tmp_path):
    coa = tmp_path / "coa.csv"
    _write_coa(coa)
    coll = indexer.build_index(csv_path=str(coa), chroma_dir=str(tmp_path / "db"), embed_fn=fake_embed)
    assert coll.count() == 3


def test_build_index_is_idempotent(tmp_path):
    coa = tmp_path / "coa.csv"
    _write_coa(coa)

    calls = {"n": 0}

    def counting_embed(texts):
        calls["n"] += 1
        return fake_embed(texts)

    db = str(tmp_path / "db")
    indexer.build_index(csv_path=str(coa), chroma_dir=db, embed_fn=counting_embed)
    indexer.build_index(csv_path=str(coa), chroma_dir=db, embed_fn=counting_embed)
    assert calls["n"] == 1  # second build is a no-op
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_indexer.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `src/spend_predictor/rag/indexer.py`:

```python
"""Build and access the persisted ChromaDB index of the chart of accounts."""
from __future__ import annotations

import csv
from typing import Callable

import chromadb

from .. import config

COLLECTION_NAME = "chart_of_accounts"

_model = None


def _default_embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with the configured sentence-transformers model (lazy-loaded)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model.encode(texts, normalize_embeddings=True).tolist()


def get_collection(chroma_dir: str | None = None):
    """Open (or create) the persisted chart-of-accounts collection."""
    client = chromadb.PersistentClient(path=chroma_dir or config.CHROMA_DIR)
    return client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def _read_accounts(csv_path: str) -> list[dict]:
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def build_index(
    csv_path: str | None = None,
    chroma_dir: str | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] = _default_embed,
):
    """Embed the chart of accounts into the collection. Idempotent: a no-op if the
    collection already holds exactly one row per account."""
    csv_path = csv_path or config.CHART_OF_ACCOUNTS_PATH
    rows = _read_accounts(csv_path)
    collection = get_collection(chroma_dir)

    if len(rows) > 0 and collection.count() == len(rows):
        return collection

    ids = [r["account_code"] for r in rows]
    documents = [
        f'{r["account_name"]}: {r["description"]} (category: {r["category"]})' for r in rows
    ]
    metadatas = [dict(r) for r in rows]
    embeddings = embed_fn(documents)
    collection.upsert(
        ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas
    )
    return collection
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_indexer.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/rag/indexer.py tests/test_indexer.py
git commit -m "feat: chroma index builder for chart of accounts (DI embedder)"
```

---

## Task 7: RAG search tool

**Files:**
- Create: `src/spend_predictor/rag/search_tool.py`
- Test: `tests/test_search_tool.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_search_tool.py`:

```python
import csv

from spend_predictor.rag import indexer, search_tool

VOCAB = ["cloud", "office", "travel", "legal", "meal"]


def fake_embed(texts):
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


def _seed(tmp_path):
    coa = tmp_path / "coa.csv"
    rows = [
        {"account_code": "6010", "account_name": "Cloud Hosting", "description": "cloud servers and hosting", "category": "IT"},
        {"account_code": "6500", "account_name": "Office Supplies", "description": "office stationery", "category": "Admin"},
    ]
    with open(coa, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_code", "account_name", "description", "category"])
        w.writeheader()
        w.writerows(rows)
    return indexer.build_index(csv_path=str(coa), chroma_dir=str(tmp_path / "db"), embed_fn=fake_embed)


def test_search_returns_most_relevant_account(tmp_path, monkeypatch):
    coll = _seed(tmp_path)
    monkeypatch.setattr(search_tool, "get_collection", lambda: coll)
    monkeypatch.setattr(search_tool, "embed_texts", fake_embed)

    tool = search_tool.ChartOfAccountsSearchTool()
    out = tool._run(query="need cloud hosting for servers", top_k=1)
    assert "6010" in out
    assert "Cloud Hosting" in out


def test_search_handles_empty_results(tmp_path, monkeypatch):
    coll = _seed(tmp_path)
    monkeypatch.setattr(search_tool, "get_collection", lambda: coll)
    monkeypatch.setattr(search_tool, "embed_texts", fake_embed)

    tool = search_tool.ChartOfAccountsSearchTool()
    out = tool._run(query="cloud", top_k=5)
    assert "6010" in out  # at least returns candidates
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_search_tool.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `src/spend_predictor/rag/search_tool.py`. Note the module-level names `get_collection`/`embed_texts` are what tests monkeypatch:

```python
"""CrewAI tool that retrieves relevant chart-of-accounts entries via RAG."""
from __future__ import annotations

from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from .indexer import _default_embed as embed_texts
from .indexer import get_collection


class ChartSearchInput(BaseModel):
    query: str = Field(..., description="Free-text description of the spend to categorize")
    top_k: int = Field(5, description="Number of candidate accounts to return")


class ChartOfAccountsSearchTool(BaseTool):
    name: str = "chart_of_accounts_search"
    description: str = (
        "Search the corporate chart of accounts for accounts relevant to a spend "
        "description. Returns candidate accounts as 'code | name | category | description'."
    )
    args_schema: Type[BaseModel] = ChartSearchInput

    def _run(self, query: str, top_k: int = 5) -> str:
        collection = get_collection()
        embeddings = embed_texts([query])
        result = collection.query(query_embeddings=embeddings, n_results=top_k)
        metadatas = (result.get("metadatas") or [[]])[0]
        if not metadatas:
            return "No matching accounts found."
        lines = [
            f'- {m["account_code"]} | {m["account_name"]} | {m["category"]} | {m["description"]}'
            for m in metadatas
        ]
        return "Candidate accounts:\n" + "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_search_tool.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/rag/search_tool.py tests/test_search_tool.py
git commit -m "feat: ChartOfAccountsSearchTool RAG retrieval tool"
```

---

## Task 8: Agent factories

**Files:**
- Create: `src/spend_predictor/agents.py`
- Test: `tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents.py`:

```python
from spend_predictor.agents import make_categorizer, make_extractor, make_verifier
from spend_predictor.rag.search_tool import ChartOfAccountsSearchTool


def test_extractor_and_verifier_have_no_tools():
    assert make_extractor().tools == []
    assert make_verifier().tools == []


def test_categorizer_has_rag_tool():
    cat = make_categorizer()
    assert any(isinstance(t, ChartOfAccountsSearchTool) for t in cat.tools)


def test_agents_have_distinct_roles():
    roles = {make_extractor().role, make_verifier().role, make_categorizer().role}
    assert len(roles) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agents.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `src/spend_predictor/agents.py`:

```python
"""Factory functions for the three pipeline agents."""
from __future__ import annotations

from crewai import Agent

from .config import get_llm
from .rag.search_tool import ChartOfAccountsSearchTool


def make_extractor() -> Agent:
    return Agent(
        role="Invoice Data Extraction Specialist",
        goal=(
            "Read raw invoice text and extract every structured field accurately: "
            "vendor, invoice number, date, currency, line items, subtotal, tax, and total."
        ),
        backstory=(
            "You are a meticulous accounts-payable clerk who has transcribed tens of "
            "thousands of invoices. You never invent values: if a field is absent you "
            "leave it null, and you copy amounts exactly as written."
        ),
        llm=get_llm(),
        tools=[],
        max_iter=10,
        verbose=False,
    )


def make_verifier() -> Agent:
    return Agent(
        role="Invoice Arithmetic Auditor",
        goal=(
            "Independently verify an extracted invoice: confirm line items sum to the "
            "subtotal and that subtotal plus tax equals the total, and list every "
            "discrepancy you find."
        ),
        backstory=(
            "You are a skeptical financial auditor who trusts nothing until the numbers "
            "reconcile. You flag mismatches precisely but never block processing."
        ),
        llm=get_llm(),
        tools=[],
        max_iter=10,
        verbose=False,
    )


def make_categorizer() -> Agent:
    return Agent(
        role="Spend Categorization Analyst",
        goal=(
            "Assign each invoice to the single best-matching account from the corporate "
            "chart of accounts, using the search tool to find candidates and choosing "
            "only from the returned options."
        ),
        backstory=(
            "You are a management accountant who codes spend to the chart of accounts. "
            "You always search for candidate accounts first and pick the closest fit, "
            "giving a confidence score and a short rationale."
        ),
        llm=get_llm(),
        tools=[ChartOfAccountsSearchTool()],
        max_iter=10,
        verbose=False,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agents.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/agents.py tests/test_agents.py
git commit -m "feat: extractor/verifier/categorizer agent factories"
```

---

## Task 9: The Flow

**Files:**
- Create: `src/spend_predictor/flow.py`
- Test: `tests/test_flow.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_flow.py`. Agents and PDF loading are faked so no LLM or PDF is needed:

```python
import csv

from spend_predictor import config, flow
from spend_predictor.models import (
    CategorizedInvoice,
    ExtractedInvoice,
    LineItem,
    VerificationResult,
)


class _FakeResult:
    def __init__(self, pydantic):
        self.pydantic = pydantic


class _FakeAgent:
    def __init__(self, pydantic):
        self._pydantic = pydantic

    def kickoff(self, *args, **kwargs):
        return _FakeResult(self._pydantic)


def _read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _install_fakes(monkeypatch, ledger_path):
    monkeypatch.setattr(config, "LEDGER_PATH", str(ledger_path))
    extracted = ExtractedInvoice(
        vendor_name="Acme Cloud",
        invoice_number="INV-1",
        invoice_date="2026-05-01",
        currency="USD",
        line_items=[LineItem(description="cloud hosting", amount=100.0)],
        subtotal=100.0,
        tax=0.0,
        total=100.0,
    )
    verification = VerificationResult(arithmetic_ok=True, discrepancies=[], notes=None)
    categorized = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting", category="IT", confidence=0.9, rationale="ok"
    )
    monkeypatch.setattr(flow, "make_extractor", lambda: _FakeAgent(extracted))
    monkeypatch.setattr(flow, "make_verifier", lambda: _FakeAgent(verification))
    monkeypatch.setattr(flow, "make_categorizer", lambda: _FakeAgent(categorized))


def test_flow_writes_processed_row(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)
    monkeypatch.setattr(flow, "extract_text", lambda p: "INVOICE Acme Cloud total 100")

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/sample.pdf"})

    rows = _read(ledger)
    assert len(rows) == 1
    assert rows[0]["status"] == "processed"
    assert rows[0]["source_file"] == "sample.pdf"
    assert rows[0]["account_code"] == "6010"


def test_flow_skips_empty_pdf_and_does_not_call_agents(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)
    monkeypatch.setattr(flow, "extract_text", lambda p: "")

    def _boom():
        raise AssertionError("agents must not run for skipped invoices")

    monkeypatch.setattr(flow, "make_extractor", lambda: _boom())

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/blank.pdf"})

    rows = _read(ledger)
    assert len(rows) == 1
    assert rows[0]["status"] == "skipped"
    assert rows[0]["notes"] == "empty PDF text"
    assert rows[0]["account_code"] == ""


def test_flow_skips_on_pdf_error(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)

    def _raise(p):
        raise ValueError("not a pdf")

    monkeypatch.setattr(flow, "extract_text", _raise)

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/broken.pdf"})

    rows = _read(ledger)
    assert rows[0]["status"] == "skipped"
    assert "not a pdf" in rows[0]["notes"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_flow.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `src/spend_predictor/flow.py`:

```python
"""The invoice-processing Flow and the run-all entry point."""
from __future__ import annotations

from pathlib import Path

from crewai.flow.flow import Flow, listen, start

from . import config
from .agents import make_categorizer, make_extractor, make_verifier
from .ledger import append_row, build_ledger_row
from .models import (
    CategorizedInvoice,
    ExtractedInvoice,
    InvoiceState,
    VerificationResult,
)
from .pdf_loader import extract_text
from .rag.indexer import build_index


class InvoiceFlow(Flow[InvoiceState]):
    """Process a single invoice: load -> extract -> verify -> categorize -> ledger."""

    @start()
    def load_invoice(self):
        try:
            text = extract_text(self.state.pdf_path)
        except Exception as exc:  # noqa: BLE001 - any parse failure means skip
            self.state.skipped = True
            self.state.skip_reason = f"PDF parse error: {exc}"
            return
        if not text.strip():
            self.state.skipped = True
            self.state.skip_reason = "empty PDF text"
            return
        self.state.invoice_text = text

    @listen(load_invoice)
    def extract(self):
        if self.state.skipped:
            return
        agent = make_extractor()
        result = agent.kickoff(
            "Extract the structured invoice data from the following invoice text. "
            "Leave any missing field null.\n\n" + self.state.invoice_text,
            response_format=ExtractedInvoice,
        )
        self.state.extracted = result.pydantic

    @listen(extract)
    def verify(self):
        if self.state.skipped:
            return
        agent = make_verifier()
        result = agent.kickoff(
            "Verify the arithmetic of this extracted invoice and list any "
            "discrepancies.\n\n" + self.state.extracted.model_dump_json(indent=2),
            response_format=VerificationResult,
        )
        self.state.verification = result.pydantic

    @listen(verify)
    def categorize(self):
        if self.state.skipped:
            return
        inv = self.state.extracted
        descriptions = "; ".join(li.description for li in inv.line_items)
        query = f"{inv.vendor_name}: {descriptions}"
        agent = make_categorizer()
        result = agent.kickoff(
            "Categorize this invoice to the single best account in the corporate "
            "chart of accounts. Use the chart_of_accounts_search tool to find "
            f"candidates for: {query}. Choose only from the returned accounts.",
            response_format=CategorizedInvoice,
        )
        self.state.categorized = result.pydantic

    @listen(categorize)
    def record_to_ledger(self):
        row = build_ledger_row(
            source_file=Path(self.state.pdf_path).name,
            skipped=self.state.skipped,
            skip_reason=self.state.skip_reason,
            extracted=self.state.extracted,
            verification=self.state.verification,
            categorized=self.state.categorized,
        )
        append_row(row, config.LEDGER_PATH)


def run_all() -> None:
    """Process every PDF in the invoices directory into the ledger."""
    invoices_dir = Path(config.INVOICES_DIR)
    pdfs = sorted(invoices_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {invoices_dir}")
        return

    build_index()  # ensure the RAG index exists (no-op if already built)

    for pdf in pdfs:
        print(f"Processing {pdf.name} ...")
        result = InvoiceFlow().kickoff(inputs={"pdf_path": str(pdf)})
        state = result.state if hasattr(result, "state") else None
        if state and state.skipped:
            print(f"  skipped: {state.skip_reason}")
        elif state and state.categorized:
            c = state.categorized
            print(f"  -> {c.account_code} {c.account_name} (confidence {c.confidence})")
    print(f"Done. Ledger: {config.LEDGER_PATH}")
```

> Note on the summary print: CrewAI's `flow.kickoff()` return value varies by
> version. The flow's own `record_to_ledger` step is the source of truth (it always
> writes the row); the per-invoice print is best-effort. If `result` is not a
> state-bearing object in your version, replace the summary block with
> `flow = InvoiceFlow(); flow.kickoff(inputs={"pdf_path": str(pdf)})` and read
> `flow.state` instead.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_flow.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full unit suite**

Run: `uv run pytest -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/spend_predictor/flow.py tests/test_flow.py
git commit -m "feat: InvoiceFlow pipeline and run_all entry point"
```

---

## Task 10: Sample data — chart of accounts + sample invoice

**Files:**
- Create: `data/chart_of_accounts.csv`
- Create: `scripts/generate_sample_invoice.py`
- Create: `data/invoices/sample_invoice.pdf` (generated)

- [ ] **Step 1: Create the sample chart of accounts**

Create `data/chart_of_accounts.csv`:

```csv
account_code,account_name,description,category
6010,Cloud Hosting & Infrastructure,cloud servers compute storage hosting and infrastructure services,IT
6020,Software Subscriptions,saas software licenses and subscription tools,IT
6030,Telecommunications,internet phone mobile and connectivity services,IT
6500,Office Supplies,stationery paper printer supplies and small office items,Admin
6510,Office Equipment,furniture monitors hardware and durable office equipment,Admin
6600,Professional Services,consulting accounting and outsourced professional work,Services
6610,Legal Fees,legal counsel attorney and compliance services,Services
6700,Marketing & Advertising,advertising campaigns marketing and promotional spend,Marketing
6800,Travel - Airfare,flights and airline tickets for business travel,Travel
6810,Travel - Lodging,hotels and accommodation for business travel,Travel
6820,Meals & Entertainment,business meals client entertainment and catering,Travel
6900,Utilities,electricity water gas and facility utilities,Facilities
6910,Rent & Lease,office rent and equipment lease payments,Facilities
7000,Shipping & Freight,courier postage shipping and freight charges,Logistics
7100,Training & Development,courses conferences training and employee development,HR
```

- [ ] **Step 2: Create the sample-invoice generator**

Create `scripts/generate_sample_invoice.py`:

```python
"""Generate a deterministic sample invoice PDF under data/invoices/."""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "data" / "invoices" / "sample_invoice.pdf"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=letter)
    lines = [
        "INVOICE",
        "Vendor: Nimbus Cloud Services Inc.",
        "Invoice Number: INV-2026-0042",
        "Invoice Date: 2026-05-15",
        "Currency: USD",
        "",
        "Description                    Qty   Unit Price     Amount",
        "Managed Kubernetes hosting      1     1200.00       1200.00",
        "Object storage (1TB)            1      80.00          80.00",
        "",
        "Subtotal:   1280.00",
        "Tax (10%):   128.00",
        "Total:      1408.00",
    ]
    y = 740
    for line in lines:
        c.drawString(72, y, line)
        y -= 18
    c.showPage()
    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Generate the sample invoice**

Run: `uv run python scripts/generate_sample_invoice.py`
Expected: prints `Wrote .../data/invoices/sample_invoice.pdf`; the file exists.

- [ ] **Step 4: Sanity-check extraction over the sample**

Run: `uv run python -c "from spend_predictor.pdf_loader import extract_text; print(extract_text('data/invoices/sample_invoice.pdf')[:80])"`
Expected: prints text beginning with `INVOICE` and the vendor line.

- [ ] **Step 5: Commit**

```bash
git add data/chart_of_accounts.csv scripts/generate_sample_invoice.py data/invoices/sample_invoice.pdf
git commit -m "feat: sample chart of accounts and generated sample invoice"
```

---

## Task 11: Entry point, env template, ignores, and docs

**Files:**
- Modify: `main.py` (root)
- Create: `.env.example`
- Create: `.gitignore`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace the root entry point**

Overwrite `main.py` with:

```python
"""Entry point: process every PDF in data/invoices/ into the ledger."""
from spend_predictor.flow import run_all


def main() -> None:
    run_all()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create `.env.example`**

Create `.env.example`:

```bash
# Local vLLM (OpenAI-compatible) endpoint
VLLM_BASE_URL=http://localhost:8000/v1
# CrewAI 1.x uses native providers (no litellm); use the hosted_vllm/ prefix for vLLM
VLLM_MODEL=hosted_vllm/google/gemma-4-E4B-it
VLLM_API_KEY=not-needed

# Embeddings for RAG retrieval
EMBEDDING_MODEL=all-MiniLM-L6-v2

# Optional path overrides (defaults shown)
# CHART_OF_ACCOUNTS_PATH=data/chart_of_accounts.csv
# INVOICES_DIR=data/invoices
# LEDGER_PATH=output/ledger.csv
# CHROMA_DIR=chroma_db
```

- [ ] **Step 3: Create `.gitignore`**

Create `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/

# Environment
.env

# Generated artifacts
output/
chroma_db/

# OS / editor
.DS_Store
```

- [ ] **Step 4: Update `README.md`**

Overwrite `README.md`:

```markdown
# Autonomous Invoice Processing & Spend Categorization (CrewAI + RAG)

A multi-agent pipeline that reads PDF invoices and codes each to a corporate
chart of accounts, writing results to a CSV ledger. Built on CrewAI (`Flow` +
`Agent.kickoff`) with RAG-backed categorization over a persisted ChromaDB index.

## Pipeline

```
PDF in data/invoices/  ->  extract text  ->  extract -> verify -> categorize  ->  output/ledger.csv
```

1. **Extract** structured fields from the invoice text.
2. **Verify** the arithmetic (line items -> subtotal -> total).
3. **Categorize** to the best chart-of-accounts entry using RAG retrieval.

## Setup

```bash
uv sync
cp .env.example .env   # then edit if your vLLM endpoint differs
```

The LLM is a local vLLM server exposing an OpenAI-compatible API at
`http://localhost:8000/v1` serving `google/gemma-4-E4B-it`. Embeddings use a
local `sentence-transformers` model (`all-MiniLM-L6-v2`, downloaded on first run).

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

Unit tests run offline (no LLM, no model download — embeddings are faked).

## Configuration

All paths and the LLM/embedding settings are configurable via `.env` (see
`.env.example`). Replace `data/chart_of_accounts.csv` with your real chart; the
ChromaDB index rebuilds automatically when the row count changes.
```

- [ ] **Step 5: Update `CLAUDE.md`**

Overwrite `CLAUDE.md`:

```markdown
# CLAUDE.md — Project Overview & Guidelines

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
  `google/gemma-4-E4B-it`. Configured via `.env` (see `.env.example`).

## Layout

- `src/spend_predictor/` — package (config, models, pdf_loader, ledger, agents,
  flow, rag/)
- `data/` — chart of accounts + input invoices
- `output/ledger.csv` — generated results
```

- [ ] **Step 6: Verify the suite still passes and the entry imports**

Run: `uv run pytest -q`
Expected: all PASS.

Run: `uv run python -c "import main; print('entry ok')"`
Expected: prints `entry ok` (no execution of the pipeline).

- [ ] **Step 7: Commit**

```bash
git add main.py .env.example .gitignore README.md CLAUDE.md
git commit -m "docs: entry point, env template, gitignore, README and CLAUDE updates"
```

---

## Task 12: Live end-to-end smoke test (manual — requires vLLM)

This task is **not automated** (it needs the vLLM server running). Run it to
confirm the real pipeline works end to end.

- [ ] **Step 1: Confirm vLLM is reachable**

Run: `curl -s http://localhost:8000/v1/models`
Expected: JSON listing `google/gemma-4-E4B-it`. If it fails, start your vLLM
server first.

- [ ] **Step 2: Run the pipeline over the sample invoice**

Run: `uv run main.py`
Expected: console shows `Processing sample_invoice.pdf ...` and a
`-> <code> <account name> (confidence ...)` line. First run downloads the
`all-MiniLM-L6-v2` embedding model.

- [ ] **Step 3: Inspect the ledger**

Run: `cat output/ledger.csv`
Expected: a header row plus one `processed` row for `sample_invoice.pdf` with a
plausible account code (e.g. `6010` Cloud Hosting), `total` `1408.0`, and
`arithmetic_ok` `True`.

- [ ] **Step 4: Confirm idempotent RAG index**

Run: `uv run main.py` again
Expected: runs without rebuilding the Chroma index (no re-embedding of the chart),
appending a second row to the ledger.

---

## Self-Review Notes

- **Spec coverage:** every spec section maps to a task — config/LLM (T2), models (T3), PDF (T4), ledger incl. skip rows (T5), RAG index (T6) + tool (T7), agents (T8), Flow incl. skip propagation (T9), sample chart + invoice (T10), entry/env/docs incl. Python 3.12 repin (T1, T11), live smoke test (T12).
- **Skip-to-ledger behavior** (spec §4, updated): implemented in T5 `build_ledger_row` and T9 flow, verified by tests.
- **DI for offline tests:** `build_index(embed_fn=...)` and monkeypatched `get_collection`/`embed_texts` keep unit tests free of model downloads and LLM calls (T6, T7, T9).
- **Known version-sensitivity:** CrewAI `LLM` attribute names (T2) and `flow.kickoff()` return shape (T9) may vary by CrewAI release; both tasks note the fallback.
