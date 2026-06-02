# Hierarchical, Buyer-Aware Categorization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `category` with a 4-level taxonomy (L1 Direct/Indirect judged from buyer context; L2/L3/leaf from the chart), add buyer-website scraping and per-line-item product web search as categorization context, and record the hierarchy + buyer in the ledger.

**Architecture:** The chart of accounts carries only L2/L3/leaf. A new `web_context` module scrapes the configured buyer's website (CrewAI keyless `ScrapeWebsiteTool`) and web-searches each invoice line item (keyless `ddgs`), both cached and injected into the categorize prompt. The toolless categorizer returns an `AccountChoice` (leaf + Direct/Indirect); grounding fills L2/L3/leaf from the chart and keeps the model's L1.

**Tech Stack:** Python 3.12, uv, CrewAI (`Flow` + `Agent.kickoff`), Pydantic v2, ChromaDB + sentence-transformers, `crewai-tools` (ScrapeWebsiteTool), `ddgs` (DuckDuckGo). Tests: pytest (offline via dependency injection).

**Spec:** `docs/superpowers/specs/2026-06-02-hierarchical-categorization-design.md`

---

## File Structure

| File | Change |
|---|---|
| `pyproject.toml` | add `crewai-tools`, `ddgs` |
| `src/spend_predictor/config.py` | add `BUYER_NAME`, `BUYER_WEBSITE`, `WEB_CONTEXT_CACHE_DIR`, `PRODUCT_SEARCH_MAX_RESULTS` |
| `.env.example`, `.gitignore` | document buyer vars; ignore web cache |
| `data/chart_of_accounts.csv` | new columns `account_code,account_name,level2,level3,description` |
| `src/spend_predictor/models.py` | add `AccountChoice`; `CategorizedInvoice` → hierarchy; `InvoiceState` gains `buyer_context`/`product_context` |
| `src/spend_predictor/rag/indexer.py` | doc text uses L2/L3 |
| `src/spend_predictor/grounding.py` | `AccountChoice` → enriched `CategorizedInvoice` |
| `src/spend_predictor/ledger.py` | columns add `buyer_name`,`level1/2/3` (drop `category`) |
| `src/spend_predictor/agents.py` | categorizer prompt: pick leaf + classify Direct/Indirect |
| `src/spend_predictor/web_context.py` | NEW — buyer scrape + product search, cached |
| `src/spend_predictor/flow.py` | `research_products` step; buyer_context input; categorize prompt; `run_all` |
| `tests/*` | new/updated to match |

> After changing the chart schema, delete the stale local index once: `rm -rf chroma_db` (gitignored; rebuilt on next run). Unit tests use their own temp dirs and are unaffected.

---

## Task 1: Dependencies, config, env, gitignore

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/spend_predictor/config.py`
- Modify: `.env.example`, `.gitignore`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add dependencies**

Run: `uv add crewai-tools ddgs`
Expected: both resolve and install on Python 3.12; `pyproject.toml` `dependencies` now includes `crewai-tools` and `ddgs`.

- [ ] **Step 2: Write the failing config test**

Add to `tests/test_config.py` (append at end):

```python
def test_buyer_and_web_context_settings():
    assert config.BUYER_NAME == ""          # unset by default
    assert config.BUYER_WEBSITE == ""
    assert config.PRODUCT_SEARCH_MAX_RESULTS == 3
    from pathlib import Path
    assert Path(config.WEB_CONTEXT_CACHE_DIR) == config.PROJECT_ROOT / "data" / "web_cache"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_buyer_and_web_context_settings -v`
Expected: FAIL (AttributeError: BUYER_NAME).

- [ ] **Step 4: Add the settings to `config.py`**

Insert after the `EMBEDDING_MODEL` line in `src/spend_predictor/config.py`:

```python
# Buyer is known beforehand (backend provides name + website); see the
# hierarchical-categorization spec. Direct/Indirect is judged from this context.
BUYER_NAME = os.getenv("BUYER_NAME", "")
BUYER_WEBSITE = os.getenv("BUYER_WEBSITE", "")
WEB_CONTEXT_CACHE_DIR = os.getenv(
    "WEB_CONTEXT_CACHE_DIR", str(PROJECT_ROOT / "data" / "web_cache")
)
PRODUCT_SEARCH_MAX_RESULTS = int(os.getenv("PRODUCT_SEARCH_MAX_RESULTS", "3"))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 6: Update `.env.example`**

Append to `.env.example`:

```bash

# Buyer (provided beforehand by the backend). Direct/Indirect is derived from
# the buyer's business context (scraped from the website).
BUYER_NAME=
BUYER_WEBSITE=
# Web context (buyer scrape + product search) cache + search breadth
# WEB_CONTEXT_CACHE_DIR=data/web_cache
PRODUCT_SEARCH_MAX_RESULTS=3
```

- [ ] **Step 7: Ignore the web cache**

Add to `.gitignore` under the generated-artifacts section:

```gitignore
data/web_cache/
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/spend_predictor/config.py tests/test_config.py .env.example .gitignore
git commit -m "feat: add crewai-tools/ddgs deps and buyer/web-context config"
```

---

## Task 2: Web context module (buyer scrape + product search)

**Files:**
- Create: `src/spend_predictor/web_context.py`
- Test: `tests/test_web_context.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_context.py`:

```python
from spend_predictor import web_context
from spend_predictor.models import LineItem


def test_buyer_context_cache_miss_then_hit(tmp_path):
    calls = {"scrape": 0, "summarize": 0}

    def scrape(url):
        calls["scrape"] += 1
        return f"raw site for {url}"

    def summarize(name, text):
        calls["summarize"] += 1
        return f"{name} is a SaaS company."

    kw = dict(name="Acme", website="https://acme.example",
              scrape_fn=scrape, summarize_fn=summarize, cache_dir=str(tmp_path))
    first = web_context.get_buyer_context(**kw)
    second = web_context.get_buyer_context(**kw)
    assert first == "Acme is a SaaS company."
    assert second == first
    assert calls == {"scrape": 1, "summarize": 1}  # second call served from cache


def test_buyer_context_blank_when_unconfigured(tmp_path):
    out = web_context.get_buyer_context(
        name="", website="", scrape_fn=lambda u: "x",
        summarize_fn=lambda n, t: "y", cache_dir=str(tmp_path)
    )
    assert out == ""


def test_product_context_searches_each_line_item(tmp_path):
    queries = []

    def search(query):
        queries.append(query)
        return [{"title": "t", "body": f"about {query}", "href": "h"}]

    def summarize(items_with_snippets):
        return "PRODUCTS:\n" + "\n".join(f"- {d}" for d, _ in items_with_snippets)

    items = [LineItem(description="cloud hosting", amount=100.0),
             LineItem(description="object storage", amount=20.0)]
    out = web_context.get_product_context(
        items, "Nimbus", search_fn=search, summarize_fn=summarize, cache_dir=str(tmp_path)
    )
    assert len(queries) == 2
    assert "Nimbus cloud hosting" in queries[0]
    assert "cloud hosting" in out and "object storage" in out


def test_product_context_empty_items(tmp_path):
    out = web_context.get_product_context(
        [], "Nimbus", search_fn=lambda q: [], summarize_fn=lambda x: "Z", cache_dir=str(tmp_path)
    )
    assert out == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_web_context.py -v`
Expected: FAIL (ModuleNotFoundError: web_context).

- [ ] **Step 3: Implement `web_context.py`**

Create `src/spend_predictor/web_context.py`:

```python
"""External web context for categorization: buyer-website scrape + product search.

Both lookups are cached to disk and accept injected primitives so unit tests run
offline. Failures degrade to empty context (never fatal).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from . import config


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def _cache_path(cache_dir: str, key: str) -> Path:
    return Path(cache_dir) / f"{_slug(key)}.txt"


def _read_cache(cache_dir: str, key: str) -> str | None:
    path = _cache_path(cache_dir, key)
    return path.read_text() if path.exists() else None


def _write_cache(cache_dir: str, key: str, value: str) -> None:
    path = _cache_path(cache_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


# --- primitives (replaceable in tests) -------------------------------------

def _scrape(url: str) -> str:
    """Scrape a website's text with CrewAI's keyless ScrapeWebsiteTool."""
    try:
        from crewai_tools import ScrapeWebsiteTool

        return ScrapeWebsiteTool(website_url=url).run() or ""
    except Exception:  # noqa: BLE001 - degrade to no context
        return ""


def _ddg_search(query: str) -> list[dict]:
    """Keyless DuckDuckGo text search; returns [{title, body, href}, ...]."""
    try:
        from ddgs import DDGS

        return list(DDGS().text(query, max_results=config.PRODUCT_SEARCH_MAX_RESULTS))
    except Exception:  # noqa: BLE001 - degrade to no results
        return []


def _summarize_buyer(name: str, text: str) -> str:
    if not text.strip():
        return f"No website context available for '{name}'."
    prompt = (
        f"In 2-3 sentences, describe the business of '{name}' based on this website "
        f"text: what they make/sell and how they earn revenue.\n\n{text[:6000]}"
    )
    return config.get_llm().call(messages=[{"role": "user", "content": prompt}]).strip()


def _summarize_products(items_with_snippets: list[tuple[str, str]]) -> str:
    blob = "\n\n".join(f"ITEM: {desc}\nSNIPPETS: {snip}" for desc, snip in items_with_snippets)
    prompt = (
        "For each invoice line item below, write one short line stating what the "
        "product/service is (use the snippets; if unclear, say 'unclear').\n\n" + blob
    )
    return config.get_llm().call(messages=[{"role": "user", "content": prompt}]).strip()


# --- public API ------------------------------------------------------------

def get_buyer_context(
    name: str = None,
    website: str = None,
    *,
    scrape_fn: Callable[[str], str] = _scrape,
    summarize_fn: Callable[[str, str], str] = _summarize_buyer,
    cache_dir: str = None,
) -> str:
    """Return a short business-context note for the buyer (cached)."""
    name = config.BUYER_NAME if name is None else name
    website = config.BUYER_WEBSITE if website is None else website
    cache_dir = config.WEB_CONTEXT_CACHE_DIR if cache_dir is None else cache_dir
    if not name and not website:
        return ""
    key = f"buyer-{name or website}"
    cached = _read_cache(cache_dir, key)
    if cached is not None:
        return cached
    note = summarize_fn(name or website, scrape_fn(website) if website else "")
    _write_cache(cache_dir, key, note)
    return note


def get_product_context(
    line_items: list,
    vendor_name: str,
    *,
    search_fn: Callable[[str], list[dict]] = _ddg_search,
    summarize_fn: Callable[[list[tuple[str, str]]], str] = _summarize_products,
    cache_dir: str = None,
) -> str:
    """Web-search each line item (cached per query) and summarize into a note."""
    cache_dir = config.WEB_CONTEXT_CACHE_DIR if cache_dir is None else cache_dir
    if not line_items:
        return ""
    items_with_snippets: list[tuple[str, str]] = []
    for item in line_items:
        query = f"{vendor_name} {item.description}".strip()
        cached = _read_cache(cache_dir, f"product-{query}")
        if cached is None:
            results = search_fn(query)
            cached = " | ".join(r.get("body", "") for r in results) or "no info found"
            _write_cache(cache_dir, f"product-{query}", cached)
        items_with_snippets.append((item.description, cached))
    return summarize_fn(items_with_snippets)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_web_context.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/spend_predictor/web_context.py tests/test_web_context.py
git commit -m "feat: web_context module (buyer website scrape + product search, cached)"
```

---

## Task 3: Core hierarchy migration (chart, models, indexer, grounding, ledger, agents, flow)

This is the atomic schema migration. It touches several files together so the full
suite stays green at the end. The flow keeps working; buyer/product context wiring
is added in Task 4 (the categorize step uses empty contexts until then).

**Files:**
- Modify: `data/chart_of_accounts.csv`
- Modify: `src/spend_predictor/models.py`
- Modify: `src/spend_predictor/rag/indexer.py`
- Modify: `src/spend_predictor/grounding.py`
- Modify: `src/spend_predictor/ledger.py`
- Modify: `src/spend_predictor/agents.py`
- Modify: `src/spend_predictor/flow.py`
- Tests: `tests/test_models.py`, `tests/test_indexer.py`, `tests/test_grounding.py`, `tests/test_ledger.py`, `tests/test_flow.py`

- [ ] **Step 1: Rewrite the sample chart**

Overwrite `data/chart_of_accounts.csv`:

```csv
account_code,account_name,level2,level3,description
6010,Cloud Hosting & Infrastructure,Technology,Cloud Infrastructure,cloud servers compute storage hosting infrastructure
6015,Third-Party APIs & Data,Technology,APIs & Data,third-party api usage data feeds model inference
6020,Software Subscriptions,Technology,SaaS & Licenses,saas software licenses subscription tools
6030,Telecommunications,Technology,Connectivity,internet phone mobile connectivity services
6500,Office Supplies,Facilities & Office,Office Supplies,stationery paper printer supplies small office items
6510,Office Equipment,Facilities & Office,Equipment,furniture monitors hardware durable office equipment
6600,Professional Services,Professional Services,Consulting,consulting outsourced professional work
6610,Legal Fees,Professional Services,Legal,legal counsel attorney compliance services
6620,Accounting & Audit,Professional Services,Accounting,accounting bookkeeping audit tax services
6700,Marketing & Advertising,Sales & Marketing,Advertising,advertising campaigns promotion marketing
6800,Travel - Airfare,Travel & Entertainment,Airfare,flights airline tickets business travel
6810,Travel - Lodging,Travel & Entertainment,Lodging,hotels accommodation business travel
6820,Meals & Entertainment,Travel & Entertainment,Meals,business meals client entertainment catering
6900,Utilities,Facilities & Office,Utilities,electricity water gas facility utilities
6910,Rent & Lease,Facilities & Office,Rent & Lease,office rent equipment lease payments
7000,Shipping & Freight,Logistics,Shipping,courier postage freight delivery
7050,Contractor - Delivery,People,Contract Labor,contractors freelancers billable project delivery
7100,Training & Development,People,Training,courses conferences training employee development
```

- [ ] **Step 2: Update models + tests**

Overwrite `src/spend_predictor/models.py`:

```python
"""Pydantic data models for the invoice pipeline and flow state."""
from __future__ import annotations

from typing import Literal

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


class AccountChoice(BaseModel):
    """Categorizer output: the chosen leaf account + the buyer-derived L1."""

    account_code: str
    account_name: str
    level1: Literal["Direct", "Indirect"]
    confidence: float  # 0..1
    rationale: str


class CategorizedInvoice(BaseModel):
    """Final, hierarchy-enriched categorization (L2/L3/leaf from the chart)."""

    account_code: str
    account_name: str
    level1: str  # Direct | Indirect (from the model, buyer-derived)
    level2: str  # from the chart
    level3: str  # from the chart
    confidence: float
    rationale: str


class InvoiceState(BaseModel):
    """Flow state for processing a single invoice."""

    pdf_path: str = ""
    invoice_text: str = ""
    buyer_context: str = ""
    product_context: str = ""
    skipped: bool = False
    skip_reason: str = ""
    errored: bool = False
    error_reason: str = ""
    extracted: ExtractedInvoice | None = None
    verification: VerificationResult | None = None
    categorized: CategorizedInvoice | None = None
    categorization_note: str = ""
```

Overwrite `tests/test_models.py`:

```python
import pytest
from pydantic import ValidationError

from spend_predictor.models import (
    AccountChoice,
    CategorizedInvoice,
    ExtractedInvoice,
    InvoiceState,
    LineItem,
    VerificationResult,
)


def test_extracted_invoice_roundtrip():
    inv = ExtractedInvoice(
        vendor_name="Acme Cloud",
        line_items=[LineItem(description="cloud hosting", amount=100.0)],
        total=100.0,
    )
    assert inv.line_items[0].amount == 100.0
    assert inv.invoice_number is None


def test_account_choice_rejects_bad_level1():
    AccountChoice(account_code="6010", account_name="Cloud", level1="Direct", confidence=0.9, rationale="r")
    with pytest.raises(ValidationError):
        AccountChoice(account_code="6010", account_name="Cloud", level1="Maybe", confidence=0.9, rationale="r")


def test_categorized_invoice_has_hierarchy():
    c = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting & Infrastructure",
        level1="Direct", level2="Technology", level3="Cloud Infrastructure",
        confidence=0.9, rationale="r",
    )
    assert (c.level1, c.level2, c.level3) == ("Direct", "Technology", "Cloud Infrastructure")


def test_invoice_state_defaults():
    s = InvoiceState()
    assert s.buyer_context == "" and s.product_context == ""
    assert s.skipped is False and s.errored is False and s.categorized is None


def test_verification_model():
    v = VerificationResult(arithmetic_ok=False, discrepancies=["x"], notes=None)
    assert v.discrepancies == ["x"]
```

- [ ] **Step 3: Update indexer doc text + tests**

In `src/spend_predictor/rag/indexer.py`, change the `documents` list comprehension inside `build_index`:

```python
    documents = [
        f'{r["level2"]} > {r["level3"]} > {r["account_name"]}: {r["description"]}'
        for r in rows
    ]
```

In `tests/test_indexer.py`, replace `_write_coa` and the seed rows so each row has
`level2`/`level3` instead of `category` (header `account_code,account_name,level2,level3,description`):

```python
def _write_coa(path):
    rows = [
        {"account_code": "6010", "account_name": "Cloud Hosting", "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud servers and hosting"},
        {"account_code": "6500", "account_name": "Office Supplies", "level2": "Facilities & Office", "level3": "Office Supplies", "description": "office stationery"},
        {"account_code": "7000", "account_name": "Travel", "level2": "Travel & Entertainment", "level3": "Airfare", "description": "travel and flights"},
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_code", "account_name", "level2", "level3", "description"])
        w.writeheader()
        w.writerows(rows)
```

And add an assertion to `test_retrieve_accounts_returns_most_relevant_first` (after the existing asserts):

```python
    assert results[0]["level2"] == "Technology"
    assert results[0]["level3"] == "Cloud Infrastructure"
```

The empty-chart test's inline writer must also use the new header:

```python
        w = csv.DictWriter(f, fieldnames=["account_code", "account_name", "level2", "level3", "description"])
```

- [ ] **Step 4: Rewrite grounding + tests**

Overwrite `src/spend_predictor/grounding.py`:

```python
"""Guardrail: ground a categorization in the real chart of accounts.

The model returns an AccountChoice (a leaf pick + a buyer-derived Direct/Indirect).
This module validates the leaf against the chart, fills L2/L3/account_name from the
chart row (snapping to the top retrieved candidate if the code is fabricated), and
carries the model's L1 through unchanged.
"""
from __future__ import annotations

from .models import AccountChoice, CategorizedInvoice


def _enrich(choice: AccountChoice, row: dict) -> CategorizedInvoice:
    return CategorizedInvoice(
        account_code=row["account_code"],
        account_name=row["account_name"],
        level1=choice.level1,
        level2=row["level2"],
        level3=row["level3"],
        confidence=choice.confidence,
        rationale=choice.rationale,
    )


def ground_categorization(
    choice: AccountChoice,
    candidates: list[dict],
    accounts_by_code: dict[str, dict],
) -> tuple[CategorizedInvoice, str]:
    """Return a (categorization, note) grounded in the chart. L2/L3/leaf come from
    the chart; L1 is the model's buyer-derived judgment."""
    code = choice.account_code
    if code in accounts_by_code:
        return _enrich(choice, accounts_by_code[code]), ""

    if candidates:
        top = candidates[0]
        note = f"categorizer returned invalid code '{code}'; snapped to '{top['account_code']}'"
        return _enrich(choice, top), note

    # Nothing to snap to: keep the model's code, blank the chart-derived levels.
    fallback = CategorizedInvoice(
        account_code=code,
        account_name=choice.account_name,
        level1=choice.level1,
        level2="",
        level3="",
        confidence=choice.confidence,
        rationale=choice.rationale,
    )
    return fallback, f"categorizer returned invalid code '{code}' (no candidates to snap to)"
```

Overwrite `tests/test_grounding.py`:

```python
from spend_predictor.grounding import ground_categorization
from spend_predictor.models import AccountChoice

CANDIDATES = [
    {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure", "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud"},
    {"account_code": "6020", "account_name": "Software Subscriptions", "level2": "Technology", "level3": "SaaS & Licenses", "description": "saas"},
]
ACCOUNTS_BY_CODE = {c["account_code"]: c for c in CANDIDATES}


def _choice(code, level1="Indirect"):
    return AccountChoice(account_code=code, account_name="whatever", level1=level1, confidence=0.9, rationale="r")


def test_valid_code_enriched_from_chart_keeps_model_l1():
    grounded, note = ground_categorization(_choice("6020", level1="Direct"), CANDIDATES, ACCOUNTS_BY_CODE)
    assert grounded.account_code == "6020"
    assert grounded.account_name == "Software Subscriptions"
    assert grounded.level2 == "Technology" and grounded.level3 == "SaaS & Licenses"
    assert grounded.level1 == "Direct"  # from the model, not the chart
    assert note == ""


def test_invalid_code_snaps_and_keeps_l1():
    grounded, note = ground_categorization(_choice("9999", level1="Direct"), CANDIDATES, ACCOUNTS_BY_CODE)
    assert grounded.account_code == "6010"
    assert grounded.level2 == "Technology" and grounded.level3 == "Cloud Infrastructure"
    assert grounded.level1 == "Direct"
    assert "9999" in note and "6010" in note


def test_invalid_code_no_candidates_blank_levels():
    grounded, note = ground_categorization(_choice("9999"), [], {})
    assert grounded.account_code == "9999"
    assert grounded.level2 == "" and grounded.level3 == ""
    assert "no candidates" in note
```

- [ ] **Step 5: Update ledger + tests**

In `src/spend_predictor/ledger.py`, replace `LEDGER_COLUMNS`:

```python
LEDGER_COLUMNS = [
    "source_file",
    "status",
    "invoice_date",
    "vendor_name",
    "buyer_name",
    "invoice_number",
    "total",
    "currency",
    "level1",
    "level2",
    "level3",
    "account_code",
    "account_name",
    "arithmetic_ok",
    "confidence",
    "notes",
]
```

Change `build_ledger_row` to accept `buyer_name` and emit the levels. Replace the
whole function signature + processed-return:

```python
def build_ledger_row(
    *,
    source_file: str,
    skipped: bool,
    skip_reason: str,
    extracted: ExtractedInvoice | None,
    verification: VerificationResult | None,
    categorized: CategorizedInvoice | None,
    categorization_note: str = "",
    errored: bool = False,
    error_reason: str = "",
    buyer_name: str = "",
) -> dict:
    """Build a ledger row dict from flow results."""
    if skipped:
        row = {col: "" for col in LEDGER_COLUMNS}
        row["source_file"] = source_file
        row["status"] = "skipped"
        row["notes"] = skip_reason
        row["buyer_name"] = buyer_name
        return row

    if errored:
        row = {col: "" for col in LEDGER_COLUMNS}
        row["source_file"] = source_file
        row["status"] = "error"
        row["notes"] = error_reason
        row["buyer_name"] = buyer_name
        return row

    note_parts: list[str] = []
    if verification and verification.discrepancies:
        note_parts.append("; ".join(verification.discrepancies))
    if verification and verification.notes:
        note_parts.append(verification.notes)
    if categorization_note:
        note_parts.append(categorization_note)
    notes = " | ".join(note_parts)

    return {
        "source_file": source_file,
        "status": "processed",
        "invoice_date": (extracted.invoice_date if extracted else "") or "",
        "vendor_name": extracted.vendor_name if extracted else "",
        "buyer_name": buyer_name,
        "invoice_number": (extracted.invoice_number if extracted else "") or "",
        "total": extracted.total if extracted else "",
        "currency": (extracted.currency if extracted else "") or "",
        "level1": categorized.level1 if categorized else "",
        "level2": categorized.level2 if categorized else "",
        "level3": categorized.level3 if categorized else "",
        "account_code": categorized.account_code if categorized else "",
        "account_name": categorized.account_name if categorized else "",
        "arithmetic_ok": verification.arithmetic_ok if verification else "",
        "confidence": categorized.confidence if categorized else "",
        "notes": notes,
    }
```

Update `tests/test_ledger.py`: the processed-row test must build a hierarchical
`CategorizedInvoice` and pass `buyer_name`. Replace `test_build_ledger_row_processed`:

```python
def test_build_ledger_row_processed():
    extracted = ExtractedInvoice(
        vendor_name="Acme Cloud", invoice_number="INV-1", invoice_date="2026-05-01",
        currency="USD", line_items=[LineItem(description="cloud hosting", amount=100.0)],
        subtotal=100.0, tax=0.0, total=100.0,
    )
    verification = VerificationResult(arithmetic_ok=True, discrepancies=[], notes=None)
    categorized = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting & Infrastructure",
        level1="Direct", level2="Technology", level3="Cloud Infrastructure",
        confidence=0.9, rationale="ok",
    )
    row = build_ledger_row(
        source_file="inv.pdf", skipped=False, skip_reason="",
        extracted=extracted, verification=verification, categorized=categorized,
        buyer_name="Acme Analytics",
    )
    assert row["status"] == "processed"
    assert row["buyer_name"] == "Acme Analytics"
    assert row["level1"] == "Direct"
    assert row["level2"] == "Technology"
    assert row["account_code"] == "6010"
    assert row["arithmetic_ok"] is True
```

Fix the import at the top of `tests/test_ledger.py` to include `CategorizedInvoice`
(it already imports the models; ensure `CategorizedInvoice` is in the import list).

- [ ] **Step 6: Update agents (categorizer prompt) **

In `src/spend_predictor/agents.py`, replace `make_categorizer`'s `goal` and
`backstory` text (keep `tools=[]`, `max_iter=5`):

```python
        goal=(
            "Choose the single best leaf account for an invoice from the provided "
            "candidate accounts, and classify the spend as Direct or Indirect based "
            "on the buyer's business context and the invoice line items. Never invent "
            "an account code; never classify the hierarchy beyond Direct/Indirect."
        ),
        backstory=(
            "You are a management accountant. You are given the buyer's business "
            "context, what the products are, and a shortlist of candidate accounts. "
            "You pick the closest account and judge whether the spend is a direct cost "
            "of the buyer's revenue (Direct) or overhead (Indirect)."
        ),
```

- [ ] **Step 7: Update flow categorize to AccountChoice + grounding (no web context yet)**

In `src/spend_predictor/flow.py`:

Change the import of models to include `AccountChoice` (replace the models import block):

```python
from .models import (
    AccountChoice,
    CategorizedInvoice,
    ExtractedInvoice,
    InvoiceState,
    VerificationResult,
)
```

Replace the body of the `categorize` step's `try` with (uses `state.buyer_context`
and `state.product_context`, which are empty until Task 4):

```python
        try:
            inv = self.state.extracted
            descriptions = "; ".join(li.description for li in inv.line_items)
            query = f"{inv.vendor_name}: {descriptions}"
            candidates = retrieve_accounts(query, top_k=5)
            candidate_lines = "\n".join(
                f"- {c['account_code']} | {c['level2']} > {c['level3']} > {c['account_name']} | {c['description']}"
                for c in candidates
            )
            line_items = "\n".join(
                f"- {li.description} (qty={li.quantity}, amount={li.amount})"
                for li in inv.line_items
            )
            agent = make_categorizer()
            result = agent.kickoff(
                "Categorize this invoice. Choose ONE candidate account code and judge "
                "Direct vs Indirect from the buyer context and line items.\n\n"
                f"Buyer context:\n{self.state.buyer_context or '(none)'}\n\n"
                f"Product context:\n{self.state.product_context or '(none)'}\n\n"
                f"Invoice line items:\n{line_items}\n\n"
                f"Candidate accounts:\n{candidate_lines}",
                response_format=AccountChoice,
            )
            accounts_by_code = {a["account_code"]: a for a in load_accounts()}
            grounded, note = ground_categorization(
                result.pydantic, candidates, accounts_by_code
            )
            self.state.categorized = grounded
            self.state.categorization_note = note
        except Exception as exc:  # noqa: BLE001 - record and move on
            self.state.errored = True
            self.state.error_reason = f"categorize failed: {exc}"
```

Update `record_to_ledger` to pass `buyer_name=config.BUYER_NAME`:

```python
        row = build_ledger_row(
            source_file=Path(self.state.pdf_path).name,
            skipped=self.state.skipped,
            skip_reason=self.state.skip_reason,
            extracted=self.state.extracted,
            verification=self.state.verification,
            categorized=self.state.categorized,
            categorization_note=self.state.categorization_note,
            errored=self.state.errored,
            error_reason=self.state.error_reason,
            buyer_name=config.BUYER_NAME,
        )
        append_row(row, config.LEDGER_PATH)
```

- [ ] **Step 8: Update flow tests for the new shapes**

In `tests/test_flow.py`, the `_install_fakes` helper must (a) make the categorizer
fake return an `AccountChoice`, and (b) provide chart rows with `level2/level3`.
Replace the relevant lines:

```python
from spend_predictor.models import (
    AccountChoice,
    CategorizedInvoice,
    ExtractedInvoice,
    LineItem,
    VerificationResult,
)
```

In `_install_fakes`, replace the `categorized = CategorizedInvoice(...)` line and the
account/monkeypatch lines with:

```python
    choice = AccountChoice(
        account_code="6010", account_name="Cloud Hosting", level1="Direct", confidence=0.9, rationale="ok"
    )
    monkeypatch.setattr(flow, "make_extractor", lambda: _FakeAgent(extracted))
    monkeypatch.setattr(flow, "make_verifier", lambda: _FakeAgent(verification))
    monkeypatch.setattr(flow, "make_categorizer", lambda: _FakeAgent(choice))
    account = {
        "account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
        "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud servers and hosting",
    }
    monkeypatch.setattr(flow, "retrieve_accounts", lambda query, top_k=5: [account])
    monkeypatch.setattr(flow, "load_accounts", lambda: [account])
```

In `test_flow_writes_processed_row`, add hierarchy/buyer assertions after the existing ones:

```python
    assert rows[0]["level1"] == "Direct"
    assert rows[0]["level2"] == "Technology"
    assert rows[0]["account_name"] == "Cloud Hosting & Infrastructure"
```

In `test_flow_snaps_hallucinated_account_code`, change the bogus categorizer to an
`AccountChoice` with a fake code:

```python
    bogus = AccountChoice(
        account_code="9999", account_name="Made Up", level1="Indirect", confidence=0.95, rationale="hallucinated"
    )
    monkeypatch.setattr(flow, "make_categorizer", lambda: _FakeAgent(bogus))
```

(The existing assertions that the row snaps to `6010` and notes contain `9999`/`6010`
remain valid.)

- [ ] **Step 9: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS (models, indexer, grounding, ledger, flow, web_context, config, pdf, agents).

- [ ] **Step 10: Commit**

```bash
git add data/chart_of_accounts.csv src/spend_predictor/ tests/
git commit -m "feat: hierarchical chart + AccountChoice + grounding/ledger/flow migration"
```

---

## Task 4: Wire buyer + product web context into the flow

**Files:**
- Modify: `src/spend_predictor/flow.py`
- Test: `tests/test_flow.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_flow.py`:

```python
def test_flow_uses_buyer_and_product_context(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)
    monkeypatch.setattr(flow, "extract_text", lambda p: "INVOICE Acme Cloud total 100")

    seen = {}

    def _fake_product_context(line_items, vendor_name):
        seen["called"] = True
        return "PRODUCTS: cloud hosting"

    monkeypatch.setattr(flow, "get_product_context", _fake_product_context)

    captured = {}

    class _CapturingAgent:
        def kickoff(self, prompt, **kwargs):
            captured["prompt"] = prompt
            from spend_predictor.models import AccountChoice
            return type("R", (), {"pydantic": AccountChoice(
                account_code="6010", account_name="Cloud", level1="Direct", confidence=0.9, rationale="ok")})()

    monkeypatch.setattr(flow, "make_categorizer", lambda: _CapturingAgent())

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/sample.pdf", "buyer_context": "Acme is a SaaS company."})

    assert seen.get("called") is True
    assert "Acme is a SaaS company." in captured["prompt"]
    assert "PRODUCTS: cloud hosting" in captured["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_flow.py::test_flow_uses_buyer_and_product_context -v`
Expected: FAIL (`flow` has no attribute `get_product_context`; product_context not in prompt).

- [ ] **Step 3: Add the research_products step and imports**

In `src/spend_predictor/flow.py`, add to imports:

```python
from .web_context import get_product_context
```

Add a new step between `verify` and `categorize`, and re-point `categorize`'s
`@listen` to it. Insert after the `verify` method:

```python
    @listen(verify)
    def research_products(self):
        if self.state.skipped or self.state.errored:
            return
        try:
            inv = self.state.extracted
            self.state.product_context = get_product_context(inv.line_items, inv.vendor_name)
        except Exception:  # noqa: BLE001 - product context is best-effort
            self.state.product_context = ""
```

Change the categorize decorator from `@listen(verify)` to `@listen(research_products)`.

- [ ] **Step 4: Resolve buyer context once in run_all and pass it in**

In `src/spend_predictor/flow.py`, add to imports:

```python
from .web_context import get_buyer_context
```

In `run_all`, after `build_index()`, resolve the buyer context and pass it to each
flow kickoff. Replace the build_index line + loop kickoff:

```python
    build_index()  # ensure the RAG index exists (no-op if already built)

    try:
        buyer_context = get_buyer_context()
    except Exception as exc:  # noqa: BLE001 - degrade to no buyer context
        print(f"  (buyer context unavailable: {exc})")
        buyer_context = ""

    for pdf in pdfs:
        print(f"Processing {pdf.name} ...")
        invoice_flow = InvoiceFlow()
        try:
            invoice_flow.kickoff(
                inputs={"pdf_path": str(pdf), "buyer_context": buyer_context}
            )
        except Exception as exc:  # noqa: BLE001 - keep processing remaining invoices
            print(f"  ERROR: {exc}")
            try:
                append_row(
                    build_ledger_row(
                        source_file=pdf.name, skipped=False, skip_reason="",
                        extracted=None, verification=None, categorized=None,
                        errored=True, error_reason=f"flow crashed: {exc}",
                        buyer_name=config.BUYER_NAME,
                    ),
                    config.LEDGER_PATH,
                )
            except Exception:  # noqa: BLE001
                pass
            continue
```

(Leave the post-kickoff summary block — skipped/error/categorized printing — as is.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_flow.py::test_flow_uses_buyer_and_product_context -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/spend_predictor/flow.py tests/test_flow.py
git commit -m "feat: inject buyer (scrape) + product (search) context into categorization"
```

---

## Task 5: Docs + as-built spec sync

**Files:**
- Modify: `README.md`, `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-06-01-spend-predictor-rag-design.md` (cross-link)

- [ ] **Step 1: Update README**

In `README.md`, update the pipeline section to describe the 4-level taxonomy and the
two web lookups, and add a Buyer configuration note. Replace the `## Configuration`
section body with:

```markdown
Set the buyer in `.env` (`BUYER_NAME`, `BUYER_WEBSITE`) — the buyer's website is
scraped once per run to judge Direct/Indirect. Line items are web-searched
(DuckDuckGo, no key) to clarify products. The chart of accounts
(`data/chart_of_accounts.csv`) provides `level2`/`level3` and the leaf account;
Direct/Indirect is derived per invoice from the buyer context, not stored in the
chart. Replace the sample chart with your real one (same columns); the ChromaDB
index rebuilds when the row count changes.
```

Update the pipeline diagram line to:

```
PDF -> extract -> verify -> research products -> categorize (leaf + Direct/Indirect) -> output/ledger.csv
```

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md`, update the Project paragraph to mention the hierarchy and web
context, and add `web_context` to the package list under Layout:

```markdown
- `src/spend_predictor/` — package (config, models, pdf_loader, ledger, agents,
  grounding, web_context, flow, rag/)
```

- [ ] **Step 3: Cross-link the original spec**

Append to the end of `docs/superpowers/specs/2026-06-01-spend-predictor-rag-design.md`:

```markdown

---

> **Superseded in part:** categorization is now hierarchical and buyer-aware. See
> `2026-06-02-hierarchical-categorization-design.md` (chart drops the flat
> `category`; L1 Direct/Indirect is derived from buyer context; ledger gains
> `buyer_name` and `level1/2/3`).
```

- [ ] **Step 4: Verify suite still green**

Run: `uv run pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/superpowers/specs/2026-06-01-spend-predictor-rag-design.md
git commit -m "docs: hierarchical, buyer-aware categorization (README, CLAUDE, spec link)"
```

---

## Task 6: Live end-to-end smoke test (manual — requires vLLM + network)

Not automated (needs the vLLM server, internet for scrape/search). Run to confirm
the real pipeline.

- [ ] **Step 1: Configure a buyer**

Set in `.env` (example):

```bash
BUYER_NAME=Anthropic
BUYER_WEBSITE=https://www.anthropic.com
```

- [ ] **Step 2: Rebuild the index (chart schema changed)**

Run: `rm -rf chroma_db`
Expected: stale index removed; it rebuilds on next run.

- [ ] **Step 3: Run the pipeline**

Run: `uv run main.py`
Expected: console shows buyer context resolved once, then per invoice a
`-> <code> <account> (confidence ...)` line. First run scrapes the buyer site and
searches line items (cached afterward).

- [ ] **Step 4: Inspect the ledger**

Run: `cat output/ledger.csv`
Expected: header includes `buyer_name,level1,level2,level3`; processed rows show a
Direct/Indirect L1, an L2/L3 path from the chart, a real `account_code`, and
`buyer_name`. Skipped/error rows blank the categorization columns.

- [ ] **Step 5: Confirm caching**

Run: `uv run main.py` again
Expected: faster — no re-scrape/re-search (served from `data/web_cache/`), index not
rebuilt.

---

## Self-Review Notes

- **Spec coverage:** chart schema (T3), AccountChoice/Literal L1 + CategorizedInvoice
  hierarchy + state fields (T3), indexer L2/L3 doc text (T3), grounding L1-from-model
  / L2-L3-from-chart (T3), ledger buyer_name+levels (T3), agents prompt (T3),
  web_context buyer scrape + per-line-item product search + cache (T2), flow
  research_products + buyer_context input + run_all once (T4), config + deps + env
  (T1), docs (T5), live test (T6).
- **Offline tests:** web_context (injected scrape/search/summarize), flow
  (monkeypatched get_product_context + buyer_context input + faked agents/retrieval)
  keep the suite free of network/LLM.
- **Green boundaries:** T3 updates the shared `CategorizedInvoice`/chart and ALL its
  callers + tests in one task, so the suite is green at every task commit; T4 is
  purely additive (web context).
- **Known version-sensitivity:** `ScrapeWebsiteTool().run()` and `ddgs.DDGS().text()`
  signatures may vary by version; both are isolated in `web_context` primitives and
  wrapped in try/except that degrades to empty context.
