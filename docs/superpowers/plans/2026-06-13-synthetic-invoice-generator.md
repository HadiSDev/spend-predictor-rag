# Synthetic Invoice Generator + ANLS Benchmark — Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate labeled synthetic invoice fixtures (PDF + structured fields + ERP journal + category labels) and a scorer that benchmarks the existing extraction/categorization pipeline against them using ANLS.

**Architecture:** A new `src/spend_predictor/synthdata/` subpackage. Labels are chosen programmatically (ground-truth by construction): `profiles` → `sampler` build an `InvoicePlan`; `content` fills realistic line-item descriptions via the local vLLM (Bespoke Curator, free-text JSON parsed by the existing `parsing.py`); `erp` builds a balanced double-entry journal; `render` turns the record into a WeasyPrint PDF; `generate` orchestrates and writes fixture bundles; `score` runs the existing `InvoiceFlow` over the PDFs and reports per-field ANLS + category accuracy.

**Tech Stack:** Python 3.12, Pydantic v2, Faker, WeasyPrint + Jinja2, Bespoke Curator (over local vLLM), `shunk031/ANLS`, pdfplumber (already present), pytest.

## Global Constraints

- Python **3.12**; managed with `uv` (`uv add ...`, `uv run pytest`).
- Reuse the existing `spend_predictor.models` schema (`ExtractedInvoice`, `LineItem`) as the structured ground-truth — do NOT define a parallel invoice schema.
- LLM access MUST avoid vLLM guided/structured decoding (free-text JSON + `spend_predictor.parsing.parse_model` only) — see memory `avoid-vllm-guided-decoding`.
- All unit tests run **offline**: stub the LLM (`generate_fn`/`enrich_fn`) and the pipeline (`run_pipeline`) via dependency injection. No network, no model download, no live vLLM in tests.
- Labels are chosen programmatically; the LLM may only fill line-item description text — it must never change a numeric or labeled field.
- One chart account per invoice (single unambiguous category label).
- New code lives under `src/spend_predictor/synthdata/`; tests under `tests/synthdata/`.

---

## File Structure

- `src/spend_predictor/synthdata/__init__.py` — package marker.
- `src/spend_predictor/synthdata/profiles.py` — `BuyerProfile`, `PROFILES`, `level1_for`.
- `src/spend_predictor/synthdata/sampler.py` — `LinePlan`, `InvoicePlan`, `sample_plans`.
- `src/spend_predictor/synthdata/content.py` — `enrich_descriptions` (+ live `_default_generate`).
- `src/spend_predictor/synthdata/erp.py` — `JournalEntry`, `build_journal`.
- `src/spend_predictor/synthdata/render/renderer.py` — `render_invoice_pdf`.
- `src/spend_predictor/synthdata/render/templates/{modern,classic}.html` — Jinja2 templates.
- `src/spend_predictor/synthdata/bundle.py` — `category_from_account`, `write_labels`, `append_manifest`, `load_fixture`.
- `src/spend_predictor/synthdata/generate.py` — `generate_dataset` + CLI.
- `src/spend_predictor/synthdata/score.py` — `anls_field`, `score_fixture`, `score_fixtures` + CLI.
- `tests/synthdata/test_*.py` — one test module per source file.

---

## Task 1: Buyer profiles

**Files:**
- Create: `src/spend_predictor/synthdata/__init__.py`
- Create: `src/spend_predictor/synthdata/profiles.py`
- Test: `tests/synthdata/__init__.py`, `tests/synthdata/test_profiles.py`

**Interfaces:**
- Produces: `BuyerProfile(name, website, country_code, vat_number, business_description, direct_level2: frozenset[str])`; `PROFILES: list[BuyerProfile]`; `level1_for(profile: BuyerProfile, level2: str) -> str` returning `"Direct"` or `"Indirect"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/synthdata/test_profiles.py
from spend_predictor.synthdata.profiles import PROFILES, BuyerProfile, level1_for


def test_level1_depends_on_buyer_business():
    saas = BuyerProfile(
        name="Nimbus SaaS A/S", website="https://nimbus.example", country_code="DK",
        vat_number="DK11111111", business_description="Cloud SaaS platform.",
        direct_level2=frozenset({"Technology"}),
    )
    law = BuyerProfile(
        name="Lex Partners", website="https://lex.example", country_code="DE",
        vat_number="DE222222222", business_description="Corporate law firm.",
        direct_level2=frozenset({"Professional Services"}),
    )
    # Same account (Technology) is Direct for the SaaS buyer, Indirect for the firm.
    assert level1_for(saas, "Technology") == "Direct"
    assert level1_for(law, "Technology") == "Indirect"
    assert level1_for(law, "Professional Services") == "Direct"


def test_profiles_are_populated_and_well_formed():
    assert len(PROFILES) >= 3
    for p in PROFILES:
        assert isinstance(p, BuyerProfile)
        assert p.name and p.country_code and p.vat_number and p.business_description
        assert isinstance(p.direct_level2, frozenset) and p.direct_level2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/synthdata/test_profiles.py -v`
Expected: FAIL (module `spend_predictor.synthdata.profiles` not found).

- [ ] **Step 3: Write minimal implementation**

```python
# src/spend_predictor/synthdata/__init__.py
"""Synthetic invoice dataset generation + benchmarking (Phase 1)."""
```

```python
# tests/synthdata/__init__.py
```

```python
# src/spend_predictor/synthdata/profiles.py
"""Buyer profiles. The buyer's business decides Direct vs Indirect (level1)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuyerProfile:
    name: str
    website: str
    country_code: str
    vat_number: str
    business_description: str
    direct_level2: frozenset[str]  # chart level2 groups that are Direct for this buyer


def level1_for(profile: BuyerProfile, level2: str) -> str:
    """Direct if the account's level2 group is core to this buyer, else Indirect."""
    return "Direct" if level2 in profile.direct_level2 else "Indirect"


PROFILES: list[BuyerProfile] = [
    BuyerProfile(
        name="Nimbus Analytics A/S", website="https://nimbus.example", country_code="DK",
        vat_number="DK12345678",
        business_description="A SaaS company selling a cloud analytics platform; "
        "its cost of revenue is cloud infrastructure and third-party data APIs.",
        direct_level2=frozenset({"Technology"}),
    ),
    BuyerProfile(
        name="Meridian Legal Partners", website="https://meridian-legal.example",
        country_code="DE", vat_number="DE222222222",
        business_description="A corporate law firm; its cost of revenue is the work "
        "of its lawyers and outside professional services.",
        direct_level2=frozenset({"Professional Services"}),
    ),
    BuyerProfile(
        name="Harbor Freight Logistics Inc.", website="https://harborfreight.example",
        country_code="US", vat_number="",
        business_description="A freight and logistics company; its cost of revenue is "
        "shipping, freight and contract delivery labor.",
        direct_level2=frozenset({"Logistics", "People"}),
    ),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/synthdata/test_profiles.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/synthdata/__init__.py src/spend_predictor/synthdata/profiles.py tests/synthdata/__init__.py tests/synthdata/test_profiles.py
git commit -m "feat(synthdata): buyer profiles with buyer-dependent Direct/Indirect rule"
```

---

## Task 2: Plan sampler

**Files:**
- Create: `src/spend_predictor/synthdata/sampler.py`
- Test: `tests/synthdata/test_sampler.py`
- Modify: `pyproject.toml` (add `faker`)

**Interfaces:**
- Consumes: `BuyerProfile`, `PROFILES`, `level1_for` (Task 1); `spend_predictor.rag.indexer.load_accounts() -> list[dict]` with keys `account_code, account_name, level2, level3, description`.
- Produces:
  - `LinePlan(quantity: float, unit_type: str, unit_price: float, amount: float, vat_code: str | None, vat_rate: float | None)`
  - `InvoicePlan(buyer: BuyerProfile, account: dict, vat_regime: str, currency: str, vendor_name: str, invoice_number: str, invoice_date: str, supplier_country_code: str | None, supplier_vat_number: str | None, buyer_country_code: str | None, buyer_vat_number: str | None, lines: list[LinePlan], subtotal: float, tax: float, total: float, level1: str)`
  - `sample_plans(n: int, seed: int, *, accounts: list[dict] | None = None, profiles: list[BuyerProfile] | None = None) -> list[InvoicePlan]`

- [ ] **Step 1: Add the Faker dependency**

Run: `uv add faker`
Expected: `faker` added to `[project.dependencies]` in `pyproject.toml`.

- [ ] **Step 2: Write the failing test**

```python
# tests/synthdata/test_sampler.py
from spend_predictor.synthdata.sampler import InvoicePlan, sample_plans

_ACCOUNTS = [
    {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
     "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud servers"},
    {"account_code": "6800", "account_name": "Travel - Airfare",
     "level2": "Travel & Entertainment", "level3": "Airfare", "description": "flights"},
]


def test_sampling_is_deterministic_for_a_seed():
    a = sample_plans(5, seed=7, accounts=_ACCOUNTS)
    b = sample_plans(5, seed=7, accounts=_ACCOUNTS)
    assert [p.invoice_number for p in a] == [p.invoice_number for p in b]
    assert [p.total for p in a] == [p.total for p in b]


def test_each_plan_reconciles_and_has_single_account():
    for p in sample_plans(20, seed=1, accounts=_ACCOUNTS):
        assert isinstance(p, InvoicePlan)
        line_sum = round(sum(l.amount for l in p.lines), 2)
        assert line_sum == round(p.subtotal, 2)
        assert round(p.subtotal + p.tax, 2) == round(p.total, 2)
        assert p.account in _ACCOUNTS  # exactly one chart account drives the invoice
        assert p.level1 in {"Direct", "Indirect"}


def test_vat_regime_controls_vat_and_country_fields():
    plans = sample_plans(40, seed=3, accounts=_ACCOUNTS)
    eu = [p for p in plans if p.vat_regime == "EU"]
    us = [p for p in plans if p.vat_regime == "US"]
    assert eu and us  # both regimes appear
    for p in eu:
        assert p.tax > 0 and p.supplier_vat_number and p.buyer_country_code
        assert all(l.vat_rate and l.vat_code for l in p.lines)
    for p in us:
        assert p.tax == 0 and not p.supplier_vat_number
        assert all(l.vat_rate in (None, 0) for l in p.lines)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/synthdata/test_sampler.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Write minimal implementation**

```python
# src/spend_predictor/synthdata/sampler.py
"""Seeded sampler that builds InvoicePlans (all ground-truth labels, no LLM)."""
from __future__ import annotations

from dataclasses import dataclass

from faker import Faker

from ..rag.indexer import load_accounts
from .profiles import PROFILES, BuyerProfile, level1_for

_UNIT_TYPES = ["pcs", "hours", "months", "units", "GB", "licenses"]
_CURRENCIES = {"EU": ["EUR", "DKK"], "US": ["USD"]}
_EU_VAT_RATES = [25.0, 21.0, 19.0]


@dataclass
class LinePlan:
    quantity: float
    unit_type: str
    unit_price: float
    amount: float
    vat_code: str | None
    vat_rate: float | None


@dataclass
class InvoicePlan:
    buyer: BuyerProfile
    account: dict
    vat_regime: str  # "EU" | "US"
    currency: str
    vendor_name: str
    invoice_number: str
    invoice_date: str
    supplier_country_code: str | None
    supplier_vat_number: str | None
    buyer_country_code: str | None
    buyer_vat_number: str | None
    lines: list[LinePlan]
    subtotal: float
    tax: float
    total: float
    level1: str


def _sample_one(fake: Faker, account: dict, profile: BuyerProfile) -> InvoicePlan:
    regime = fake.random_element(["EU", "US"])
    currency = fake.random_element(_CURRENCIES[regime])
    vat_rate = fake.random_element(_EU_VAT_RATES) if regime == "EU" else 0.0

    n_lines = fake.random_int(1, 4)
    lines: list[LinePlan] = []
    for _ in range(n_lines):
        qty = float(fake.random_int(1, 20))
        unit_price = round(fake.random_int(500, 200000) / 100.0, 2)
        amount = round(qty * unit_price, 2)
        lines.append(LinePlan(
            quantity=qty, unit_type=fake.random_element(_UNIT_TYPES),
            unit_price=unit_price, amount=amount,
            vat_code=("S" if regime == "EU" else None),
            vat_rate=(vat_rate if regime == "EU" else None),
        ))

    subtotal = round(sum(l.amount for l in lines), 2)
    tax = round(subtotal * vat_rate / 100.0, 2)
    total = round(subtotal + tax, 2)

    supplier_cc = fake.random_element(["DE", "FR", "NL", "DK"]) if regime == "EU" else "US"
    supplier_vat = f"{supplier_cc}{fake.numerify('#########')}" if regime == "EU" else ""

    return InvoicePlan(
        buyer=profile, account=account, vat_regime=regime, currency=currency,
        vendor_name=fake.company(),
        invoice_number=fake.numerify("INV-####-####"),
        invoice_date=fake.date(pattern="%Y-%m-%d"),
        supplier_country_code=supplier_cc,
        supplier_vat_number=supplier_vat or None,
        buyer_country_code=(profile.country_code if regime == "EU" else profile.country_code or None),
        buyer_vat_number=(profile.vat_number or None) if regime == "EU" else (profile.vat_number or None),
        lines=lines, subtotal=subtotal, tax=tax, total=total,
        level1=level1_for(profile, account["level2"]),
    )


def sample_plans(
    n: int, seed: int, *,
    accounts: list[dict] | None = None,
    profiles: list[BuyerProfile] | None = None,
) -> list[InvoicePlan]:
    """Return `n` deterministic InvoicePlans for the given seed."""
    accounts = accounts if accounts is not None else load_accounts()
    profiles = profiles if profiles is not None else PROFILES
    fake = Faker()
    Faker.seed(seed)
    fake.seed_instance(seed)
    return [
        _sample_one(fake, fake.random_element(accounts), fake.random_element(profiles))
        for _ in range(n)
    ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/synthdata/test_sampler.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/spend_predictor/synthdata/sampler.py tests/synthdata/test_sampler.py
git commit -m "feat(synthdata): seeded InvoicePlan sampler (labels, VAT regimes)"
```

---

## Task 3: LLM description enrichment

**Files:**
- Create: `src/spend_predictor/synthdata/content.py`
- Test: `tests/synthdata/test_content.py`
- Modify: `pyproject.toml` (add `bespokelabs-curator`)

**Interfaces:**
- Consumes: `InvoicePlan`, `LinePlan` (Task 2); `spend_predictor.models.ExtractedInvoice`, `LineItem`; `spend_predictor.parsing.parse_model`.
- Produces: `enrich_descriptions(plan: InvoicePlan, *, generate_fn: Callable[[str], str] = _default_generate, cryptic: bool = False) -> ExtractedInvoice`. `generate_fn` takes a prompt and returns free-text JSON `{"descriptions": [...]}`; the default routes to local vLLM via Curator (free-text, parsed by `parsing.py`).

- [ ] **Step 1: Add the Curator dependency**

Run: `uv add bespokelabs-curator`
Expected: dependency added (used only by the live `_default_generate`; tests stub `generate_fn`).

- [ ] **Step 2: Write the failing test**

```python
# tests/synthdata/test_content.py
import json

from spend_predictor.models import ExtractedInvoice
from spend_predictor.synthdata.content import enrich_descriptions
from spend_predictor.synthdata.sampler import sample_plans

_ACCOUNTS = [{"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
              "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud servers"}]


def test_enrich_fills_descriptions_and_preserves_labels():
    plan = sample_plans(1, seed=2, accounts=_ACCOUNTS)[0]
    captured = {}

    def fake_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        descs = [f"Item {i}" for i in range(len(plan.lines))]
        return json.dumps({"descriptions": descs})

    inv = enrich_descriptions(plan, generate_fn=fake_generate)

    assert isinstance(inv, ExtractedInvoice)
    assert [li.description for li in inv.line_items] == [f"Item {i}" for i in range(len(plan.lines))]
    # numeric/label fields come straight from the plan, untouched by the LLM
    assert inv.total == plan.total and inv.subtotal == plan.subtotal
    assert inv.vendor_name == plan.vendor_name
    assert len(inv.line_items) == len(plan.lines)
    assert inv.line_items[0].amount == plan.lines[0].amount
    assert "Cloud Hosting & Infrastructure" in captured["prompt"]  # account context given


def test_enrich_falls_back_when_count_mismatch():
    plan = sample_plans(1, seed=5, accounts=_ACCOUNTS)[0]

    def bad_generate(prompt: str) -> str:
        return '{"descriptions": ["only one"]}'  # wrong count

    inv = enrich_descriptions(plan, generate_fn=bad_generate)
    # falls back to a deterministic per-line placeholder, never crashes
    assert len(inv.line_items) == len(plan.lines)
    assert all(li.description for li in inv.line_items)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/synthdata/test_content.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Write minimal implementation**

```python
# src/spend_predictor/synthdata/content.py
"""Fill realistic line-item descriptions via the local model (free-text JSON).

Labels and numbers come from the InvoicePlan; the model only writes description
text. We avoid vLLM guided decoding (see memory avoid-vllm-guided-decoding) by
prompting for JSON and parsing it with spend_predictor.parsing.
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from ..models import ExtractedInvoice, LineItem
from ..parsing import parse_model
from .sampler import InvoicePlan


class _Descriptions(BaseModel):
    descriptions: list[str] = Field(description="One short line-item description per line.")


def _build_prompt(plan: InvoicePlan, cryptic: bool) -> str:
    acct = plan.account
    style = (
        "Make each description realistic but TERSE and slightly cryptic, like a real "
        "vendor's billing label (abbreviations, SKUs)."
        if cryptic else
        "Make each description a clear, realistic product/service name."
    )
    lines = "\n".join(
        f"- line {i + 1}: quantity {l.quantity} {l.unit_type}, amount {l.amount}"
        for i, l in enumerate(plan.lines)
    )
    return (
        f"You are writing line items for an invoice from vendor '{plan.vendor_name}'.\n"
        f"All lines belong to this expense account: {acct['account_name']} "
        f"({acct['level2']} > {acct['level3']}) — {acct['description']}.\n"
        f"{style}\n"
        f"Write EXACTLY {len(plan.lines)} descriptions, one per line below:\n{lines}\n\n"
        'Return ONLY JSON: {"descriptions": ["...", "..."]}'
    )


def _default_generate(prompt: str) -> str:  # pragma: no cover - live path
    """Generate via Bespoke Curator over the local vLLM (free-text, no guided decoding)."""
    from bespokelabs import curator

    from .. import config

    llm = curator.LLM(
        model_name=config.VLLM_MODEL.replace("hosted_vllm/", ""),
        backend="vllm",
        backend_params={"base_url": config.VLLM_BASE_URL, "api_key": config.VLLM_API_KEY},
    )
    return str(llm(prompt).dataset[0]["response"])


def enrich_descriptions(
    plan: InvoicePlan, *,
    generate_fn: Callable[[str], str] = _default_generate,
    cryptic: bool = False,
) -> ExtractedInvoice:
    """Return an ExtractedInvoice from the plan, with LLM-written descriptions."""
    try:
        parsed = parse_model(generate_fn(_build_prompt(plan, cryptic)), _Descriptions)
        descriptions = parsed.descriptions
        if len(descriptions) != len(plan.lines):
            raise ValueError("description count mismatch")
    except Exception:  # noqa: BLE001 - description text is best-effort, never fatal
        descriptions = [
            f"{plan.account['account_name']} item {i + 1}" for i in range(len(plan.lines))
        ]

    line_items = [
        LineItem(
            description=desc, quantity=l.quantity, unit_type=l.unit_type,
            unit_price=l.unit_price, amount=l.amount, vat_code=l.vat_code, vat_rate=l.vat_rate,
        )
        for desc, l in zip(descriptions, plan.lines)
    ]
    return ExtractedInvoice(
        vendor_name=plan.vendor_name,
        supplier_country_code=plan.supplier_country_code,
        supplier_vat_number=plan.supplier_vat_number,
        buyer_country_code=plan.buyer_country_code,
        buyer_vat_number=plan.buyer_vat_number,
        invoice_number=plan.invoice_number,
        invoice_date=plan.invoice_date,
        currency=plan.currency,
        line_items=line_items,
        subtotal=plan.subtotal, tax=plan.tax, total=plan.total,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/synthdata/test_content.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/spend_predictor/synthdata/content.py tests/synthdata/test_content.py
git commit -m "feat(synthdata): LLM description enrichment (free-text JSON, label-preserving)"
```

---

## Task 4: ERP double-entry journal

**Files:**
- Create: `src/spend_predictor/synthdata/erp.py`
- Test: `tests/synthdata/test_erp.py`

**Interfaces:**
- Consumes: `spend_predictor.models.ExtractedInvoice`.
- Produces: `JournalEntry(account_code: str, account_name: str, debit: float, credit: float)`; `build_journal(invoice: ExtractedInvoice, account_code: str, account_name: str) -> list[JournalEntry]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/synthdata/test_erp.py
from spend_predictor.models import ExtractedInvoice, LineItem
from spend_predictor.synthdata.erp import build_journal


def _invoice(tax: float) -> ExtractedInvoice:
    return ExtractedInvoice(
        vendor_name="ACME", line_items=[LineItem(description="x", amount=100.0)],
        subtotal=100.0, tax=tax, total=round(100.0 + tax, 2),
    )


def test_journal_balances_with_vat():
    j = build_journal(_invoice(25.0), "6010", "Cloud Hosting & Infrastructure")
    assert round(sum(e.debit for e in j), 2) == round(sum(e.credit for e in j), 2) == 125.0
    expense = next(e for e in j if e.account_code == "6010")
    assert expense.debit == 100.0
    assert any(e.account_code == "1300" and e.debit == 25.0 for e in j)   # VAT input
    assert any(e.account_code == "2000" and e.credit == 125.0 for e in j)  # AP


def test_journal_balances_without_vat():
    j = build_journal(_invoice(0.0), "6800", "Travel - Airfare")
    assert round(sum(e.debit for e in j), 2) == round(sum(e.credit for e in j), 2) == 100.0
    assert not any(e.account_code == "1300" for e in j)  # no VAT line when tax is 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/synthdata/test_erp.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# src/spend_predictor/synthdata/erp.py
"""Build a balanced double-entry journal for a synthetic invoice (AP booking)."""
from __future__ import annotations

from dataclasses import dataclass

from ..models import ExtractedInvoice

AP_CODE, AP_NAME = "2000", "Accounts Payable"
VAT_INPUT_CODE, VAT_INPUT_NAME = "1300", "VAT Input (Receivable)"


@dataclass
class JournalEntry:
    account_code: str
    account_name: str
    debit: float
    credit: float


def build_journal(
    invoice: ExtractedInvoice, account_code: str, account_name: str
) -> list[JournalEntry]:
    """Dr expense (net) + Dr VAT input (tax) ... Cr accounts payable (total)."""
    net = round(invoice.subtotal or 0.0, 2)
    tax = round(invoice.tax or 0.0, 2)
    total = round(invoice.total, 2)
    entries = [JournalEntry(account_code, account_name, debit=net, credit=0.0)]
    if tax > 0:
        entries.append(JournalEntry(VAT_INPUT_CODE, VAT_INPUT_NAME, debit=tax, credit=0.0))
    entries.append(JournalEntry(AP_CODE, AP_NAME, debit=0.0, credit=total))
    return entries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/synthdata/test_erp.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/synthdata/erp.py tests/synthdata/test_erp.py
git commit -m "feat(synthdata): balanced double-entry journal builder"
```

---

## Task 5: WeasyPrint renderer + templates

**Files:**
- Create: `src/spend_predictor/synthdata/render/__init__.py`
- Create: `src/spend_predictor/synthdata/render/renderer.py`
- Create: `src/spend_predictor/synthdata/render/templates/modern.html`
- Create: `src/spend_predictor/synthdata/render/templates/classic.html`
- Test: `tests/synthdata/test_renderer.py`
- Modify: `pyproject.toml` (add `weasyprint`, `jinja2`)

**Interfaces:**
- Consumes: `spend_predictor.models.ExtractedInvoice`.
- Produces: `render_invoice_pdf(invoice: ExtractedInvoice, out_path: Path, *, buyer_name: str, template_name: str = "modern") -> Path`. Templates live in `render/templates/<name>.html`.

- [ ] **Step 1: Install system libs and Python deps**

Run:
```bash
sudo apt-get update && sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev libcairo2 libcairo2-dev
uv add weasyprint jinja2
```
Expected: WeasyPrint imports without error (`uv run python -c "import weasyprint"`).

- [ ] **Step 2: Write the failing test**

```python
# tests/synthdata/test_renderer.py
import pdfplumber

from spend_predictor.models import ExtractedInvoice, LineItem
from spend_predictor.synthdata.render.renderer import render_invoice_pdf


def _invoice() -> ExtractedInvoice:
    return ExtractedInvoice(
        vendor_name="Nimbus Cloud Services Inc.", invoice_number="INV-2026-0042",
        invoice_date="2026-05-15", currency="USD",
        line_items=[LineItem(description="Managed Kubernetes hosting", quantity=1,
                             unit_type="months", unit_price=1200.0, amount=1200.0)],
        subtotal=1200.0, tax=0.0, total=1200.0,
    )


def test_render_produces_pdf_with_key_text(tmp_path):
    out = render_invoice_pdf(_invoice(), tmp_path / "inv.pdf", buyer_name="Acme Buyer Ltd")
    assert out.exists() and out.stat().st_size > 0
    with pdfplumber.open(out) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    assert "Nimbus Cloud Services Inc." in text
    assert "INV-2026-0042" in text
    assert "1200" in text
    assert "Acme Buyer Ltd" in text


def test_classic_template_also_renders(tmp_path):
    out = render_invoice_pdf(_invoice(), tmp_path / "c.pdf", buyer_name="Acme",
                             template_name="classic")
    assert out.exists() and out.stat().st_size > 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/synthdata/test_renderer.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Write the templates and renderer**

```html
<!-- src/spend_predictor/synthdata/render/templates/modern.html -->
<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { font-family: 'Helvetica', sans-serif; color: #1a1a1a; margin: 40px; }
  h1 { color: #2b6cb0; letter-spacing: 2px; }
  .row { display: flex; justify-content: space-between; }
  table { width: 100%; border-collapse: collapse; margin-top: 24px; }
  th { background: #2b6cb0; color: #fff; text-align: left; padding: 8px; }
  td { border-bottom: 1px solid #e2e8f0; padding: 8px; }
  .totals { margin-top: 16px; width: 40%; margin-left: auto; }
</style></head><body>
  <h1>INVOICE</h1>
  <div class="row">
    <div>
      <strong>{{ inv.vendor_name }}</strong><br>
      {% if inv.supplier_country_code %}Country: {{ inv.supplier_country_code }}<br>{% endif %}
      {% if inv.supplier_vat_number %}VAT: {{ inv.supplier_vat_number }}{% endif %}
    </div>
    <div>
      Invoice #: {{ inv.invoice_number }}<br>
      Date: {{ inv.invoice_date }}<br>
      Currency: {{ inv.currency }}
    </div>
  </div>
  <div style="margin-top:16px">Bill to: <strong>{{ buyer_name }}</strong>
    {% if inv.buyer_vat_number %} — VAT {{ inv.buyer_vat_number }}{% endif %}</div>
  <table><thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th>Unit Price</th>
    <th>VAT</th><th>Amount</th></tr></thead><tbody>
    {% for li in inv.line_items %}<tr>
      <td>{{ li.description }}</td><td>{{ li.quantity }}</td><td>{{ li.unit_type }}</td>
      <td>{{ li.unit_price }}</td><td>{{ li.vat_rate }}</td><td>{{ li.amount }}</td>
    </tr>{% endfor %}
  </tbody></table>
  <table class="totals">
    <tr><td>Subtotal</td><td>{{ inv.subtotal }}</td></tr>
    <tr><td>Tax</td><td>{{ inv.tax }}</td></tr>
    <tr><td><strong>Total</strong></td><td><strong>{{ inv.total }} {{ inv.currency }}</strong></td></tr>
  </table>
</body></html>
```

```html
<!-- src/spend_predictor/synthdata/render/templates/classic.html -->
<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { font-family: 'Times New Roman', serif; margin: 50px; }
  .head { text-align: center; border-bottom: 2px solid #000; padding-bottom: 8px; }
  table { width: 100%; border-collapse: collapse; margin-top: 20px; }
  td, th { border: 1px solid #000; padding: 6px; text-align: left; }
  .totals td { border: none; }
</style></head><body>
  <div class="head"><h2>{{ inv.vendor_name }}</h2>
    {% if inv.supplier_vat_number %}VAT {{ inv.supplier_vat_number }} · {% endif %}
    {{ inv.supplier_country_code or "" }}</div>
  <p>Invoice {{ inv.invoice_number }} &nbsp; Date {{ inv.invoice_date }}<br>
     Bill to: {{ buyer_name }}{% if inv.buyer_vat_number %} (VAT {{ inv.buyer_vat_number }}){% endif %}</p>
  <table><tr><th>Description</th><th>Qty</th><th>Unit</th><th>Price</th><th>Amount</th></tr>
    {% for li in inv.line_items %}<tr>
      <td>{{ li.description }}</td><td>{{ li.quantity }} {{ li.unit_type }}</td>
      <td>{{ li.unit_type }}</td><td>{{ li.unit_price }}</td><td>{{ li.amount }}</td>
    </tr>{% endfor %}</table>
  <table class="totals" style="margin-top:14px">
    <tr><td>Subtotal:</td><td>{{ inv.subtotal }}</td></tr>
    <tr><td>Tax:</td><td>{{ inv.tax }}</td></tr>
    <tr><td>Total:</td><td>{{ inv.total }} {{ inv.currency }}</td></tr>
  </table>
</body></html>
```

```python
# src/spend_predictor/synthdata/render/__init__.py
```

```python
# src/spend_predictor/synthdata/render/renderer.py
"""Render an ExtractedInvoice to a text-layer PDF via Jinja2 + WeasyPrint."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...models import ExtractedInvoice

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_invoice_pdf(
    invoice: ExtractedInvoice, out_path: Path, *,
    buyer_name: str, template_name: str = "modern",
) -> Path:
    """Render `invoice` to a PDF at `out_path` and return the path."""
    from weasyprint import HTML  # local import keeps module import light

    html = _env.get_template(f"{template_name}.html").render(inv=invoice, buyer_name=buyer_name)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(out_path))
    return out_path
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/synthdata/test_renderer.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/spend_predictor/synthdata/render tests/synthdata/test_renderer.py
git commit -m "feat(synthdata): WeasyPrint invoice renderer with two templates"
```

---

## Task 6: Fixture bundle (labels + manifest)

**Files:**
- Create: `src/spend_predictor/synthdata/bundle.py`
- Test: `tests/synthdata/test_bundle.py`

**Interfaces:**
- Consumes: `spend_predictor.models.ExtractedInvoice`; `BuyerProfile` (Task 1); `JournalEntry` (Task 4).
- Produces:
  - `category_from_account(account: dict, level1: str) -> dict` → `{account_code, account_name, level1, level2, level3}`
  - `write_labels(fixture_dir: Path, *, invoice: ExtractedInvoice, category: dict, buyer: BuyerProfile, journal: list[JournalEntry]) -> Path` (writes `labels.json`)
  - `append_manifest(manifest_path: Path, entry: dict) -> None` (one JSON object per line)
  - `load_fixture(fixture_dir: Path) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/synthdata/test_bundle.py
import json

from spend_predictor.models import ExtractedInvoice, LineItem
from spend_predictor.synthdata.bundle import (
    append_manifest, category_from_account, load_fixture, write_labels,
)
from spend_predictor.synthdata.erp import build_journal
from spend_predictor.synthdata.profiles import PROFILES


def test_category_from_account():
    acct = {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
            "level2": "Technology", "level3": "Cloud Infrastructure", "description": "x"}
    cat = category_from_account(acct, "Direct")
    assert cat == {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
                   "level1": "Direct", "level2": "Technology", "level3": "Cloud Infrastructure"}


def test_write_and_load_fixture_roundtrip(tmp_path):
    inv = ExtractedInvoice(vendor_name="ACME",
                           line_items=[LineItem(description="x", amount=100.0)],
                           subtotal=100.0, tax=0.0, total=100.0)
    cat = {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
           "level1": "Direct", "level2": "Technology", "level3": "Cloud Infrastructure"}
    journal = build_journal(inv, "6010", "Cloud Hosting & Infrastructure")
    fdir = tmp_path / "0001"
    write_labels(fdir, invoice=inv, category=cat, buyer=PROFILES[0], journal=journal)

    loaded = load_fixture(fdir)
    assert loaded["category"] == cat
    assert loaded["invoice"]["total"] == 100.0
    assert loaded["buyer"]["name"] == PROFILES[0].name
    assert loaded["buyer"]["business_description"] == PROFILES[0].business_description
    assert len(loaded["journal"]) == len(journal)


def test_append_manifest_writes_one_object_per_line(tmp_path):
    mp = tmp_path / "manifest.jsonl"
    append_manifest(mp, {"id": "0001", "account_code": "6010"})
    append_manifest(mp, {"id": "0002", "account_code": "6800"})
    lines = mp.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["id"] == "0002"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/synthdata/test_bundle.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# src/spend_predictor/synthdata/bundle.py
"""Write/read fixture bundles: labels.json per fixture + a manifest.jsonl index."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..models import ExtractedInvoice
from .erp import JournalEntry
from .profiles import BuyerProfile


def category_from_account(account: dict, level1: str) -> dict:
    return {
        "account_code": account["account_code"],
        "account_name": account["account_name"],
        "level1": level1,
        "level2": account["level2"],
        "level3": account["level3"],
    }


def write_labels(
    fixture_dir: Path, *,
    invoice: ExtractedInvoice, category: dict,
    buyer: BuyerProfile, journal: list[JournalEntry],
) -> Path:
    """Write labels.json into fixture_dir (ground-truth for the fixture's PDF)."""
    fixture_dir = Path(fixture_dir)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    labels = {
        "invoice": invoice.model_dump(),
        "category": category,
        "buyer": {
            "name": buyer.name, "website": buyer.website,
            "country_code": buyer.country_code, "vat_number": buyer.vat_number,
            "business_description": buyer.business_description,
        },
        "journal": [asdict(e) for e in journal],
    }
    path = fixture_dir / "labels.json"
    path.write_text(json.dumps(labels, indent=2))
    return path


def append_manifest(manifest_path: Path, entry: dict) -> None:
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def load_fixture(fixture_dir: Path) -> dict:
    """Load a fixture's labels.json (the PDF sits beside it as invoice.pdf)."""
    return json.loads((Path(fixture_dir) / "labels.json").read_text())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/synthdata/test_bundle.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/synthdata/bundle.py tests/synthdata/test_bundle.py
git commit -m "feat(synthdata): fixture bundle writer/loader + manifest"
```

---

## Task 7: Generator orchestrator + CLI

**Files:**
- Create: `src/spend_predictor/synthdata/generate.py`
- Test: `tests/synthdata/test_generate.py`

**Interfaces:**
- Consumes: `sample_plans` (Task 2); `enrich_descriptions` (Task 3); `build_journal` (Task 4); `render_invoice_pdf` (Task 5); `category_from_account`, `write_labels`, `append_manifest` (Task 6).
- Produces: `generate_dataset(n: int, seed: int, out_dir: Path, *, enrich_fn=enrich_descriptions, render_fn=render_invoice_pdf, cryptic: bool = False) -> int` (returns number of fixtures written); CLI `python -m spend_predictor.synthdata.generate --n N --seed S --out DIR [--cryptic]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/synthdata/test_generate.py
import json

from spend_predictor.synthdata.generate import generate_dataset

_ACCOUNTS = [{"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
              "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud"}]


def test_generate_writes_bundles_and_manifest(tmp_path, monkeypatch):
    import spend_predictor.synthdata.generate as gen

    # Offline: deterministic chart, stub enrichment, fake renderer (no WeasyPrint).
    monkeypatch.setattr(gen, "load_accounts", lambda: _ACCOUNTS)

    def fake_enrich(plan, cryptic=False):
        from spend_predictor.synthdata.content import enrich_descriptions
        return enrich_descriptions(plan, generate_fn=lambda p: '{"descriptions": ' +
                                   json.dumps([f"item {i}" for i in range(len(plan.lines))]) + '}')

    def fake_render(invoice, out_path, *, buyer_name, template_name="modern"):
        from pathlib import Path
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)

    n = generate_dataset(3, seed=7, out_dir=tmp_path, enrich_fn=fake_enrich, render_fn=fake_render)

    assert n == 3
    manifest = (tmp_path / "manifest.jsonl").read_text().splitlines()
    assert len(manifest) == 3
    for entry in (json.loads(line) for line in manifest):
        fdir = tmp_path / entry["id"]
        assert (fdir / "invoice.pdf").exists()
        labels = json.loads((fdir / "labels.json").read_text())
        assert labels["category"]["account_code"] == "6010"
        assert labels["invoice"]["line_items"]


def test_generate_skips_failed_items_without_aborting(tmp_path, monkeypatch):
    import spend_predictor.synthdata.generate as gen
    monkeypatch.setattr(gen, "load_accounts", lambda: _ACCOUNTS)

    calls = {"n": 0}

    def flaky_render(invoice, out_path, *, buyer_name, template_name="modern"):
        from pathlib import Path
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("render boom")
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)

    def fake_enrich(plan, cryptic=False):
        from spend_predictor.synthdata.content import enrich_descriptions
        return enrich_descriptions(plan, generate_fn=lambda p: '{"descriptions": ' +
                                   json.dumps(["x" for _ in plan.lines]) + '}')

    n = generate_dataset(3, seed=1, out_dir=tmp_path, enrich_fn=fake_enrich, render_fn=flaky_render)
    assert n == 2  # one item failed and was skipped, batch continued
    assert len((tmp_path / "manifest.jsonl").read_text().splitlines()) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/synthdata/test_generate.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# src/spend_predictor/synthdata/generate.py
"""Orchestrate plan -> enrich -> render -> ERP -> fixture bundle. CLI entry point."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..rag.indexer import load_accounts
from .bundle import append_manifest, category_from_account, write_labels
from .content import enrich_descriptions
from .erp import build_journal
from .render.renderer import render_invoice_pdf
from .sampler import sample_plans


def generate_dataset(
    n: int, seed: int, out_dir: Path, *,
    enrich_fn=enrich_descriptions, render_fn=render_invoice_pdf, cryptic: bool = False,
) -> int:
    """Generate `n` fixture bundles under out_dir. Returns the number written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.jsonl"
    accounts = load_accounts()
    plans = sample_plans(n, seed, accounts=accounts)

    written = 0
    for i, plan in enumerate(plans):
        fixture_id = f"{i:05d}"
        fdir = out_dir / fixture_id
        try:
            invoice = enrich_fn(plan, cryptic=cryptic)
            fdir.mkdir(parents=True, exist_ok=True)
            render_fn(invoice, fdir / "invoice.pdf", buyer_name=plan.buyer.name,
                      template_name=("classic" if i % 2 else "modern"))
            category = category_from_account(plan.account, plan.level1)
            journal = build_journal(invoice, plan.account["account_code"],
                                    plan.account["account_name"])
            write_labels(fdir, invoice=invoice, category=category,
                         buyer=plan.buyer, journal=journal)
            append_manifest(manifest, {
                "id": fixture_id, "account_code": plan.account["account_code"],
                "level1": plan.level1, "vat_regime": plan.vat_regime,
                "buyer": plan.buyer.name,
            })
            written += 1
        except Exception as exc:  # noqa: BLE001 - skip the item, keep the batch going
            print(f"  skip {fixture_id}: {exc}")
    print(f"Wrote {written}/{n} fixtures to {out_dir}")
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic invoice fixtures.")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("data/synthetic"))
    ap.add_argument("--cryptic", action="store_true",
                    help="ask the model for terse/cryptic line-item descriptions")
    args = ap.parse_args()
    generate_dataset(args.n, args.seed, args.out, cryptic=args.cryptic)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/synthdata/test_generate.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/synthdata/generate.py tests/synthdata/test_generate.py
git commit -m "feat(synthdata): dataset generator orchestrator + CLI"
```

---

## Task 8: ANLS scorer + CLI

**Files:**
- Create: `src/spend_predictor/synthdata/score.py`
- Test: `tests/synthdata/test_score.py`
- Modify: `pyproject.toml` (add `anls`)

**Interfaces:**
- Consumes: `load_fixture` (Task 6); `spend_predictor.models.ExtractedInvoice`, `CategorizedInvoice`; `spend_predictor.flow.InvoiceFlow`, `spend_predictor.rag.indexer.load_accounts`/`build_index` (live pipeline).
- Produces:
  - `anls_field(pred: str, gold: str) -> float`
  - `score_fixture(labels: dict, extracted: ExtractedInvoice | None, categorized: CategorizedInvoice | None) -> dict`
  - `score_fixtures(fixtures_dir: Path, *, run_pipeline=_default_run_pipeline) -> dict`
  - `_default_run_pipeline(pdf_path: str, buyer_context: str) -> tuple[ExtractedInvoice | None, CategorizedInvoice | None]`
  - CLI `python -m spend_predictor.synthdata.score --fixtures DIR`

- [ ] **Step 1: Add the ANLS dependency**

Run: `uv add "anls @ git+https://github.com/shunk031/ANLS"`
Expected: `from anls import anls_score` importable (`uv run python -c "from anls import anls_score"`).

- [ ] **Step 2: Write the failing test**

```python
# tests/synthdata/test_score.py
import json

from spend_predictor.models import CategorizedInvoice, ExtractedInvoice, LineItem
from spend_predictor.synthdata.score import anls_field, score_fixture, score_fixtures


def test_anls_field_rewards_near_matches():
    assert anls_field("Nimbus Cloud Services Inc.", "Nimbus Cloud Services Inc.") == 1.0
    assert anls_field("", "Anything") == 0.0
    assert anls_field("Nimbus Cloud Servces Inc", "Nimbus Cloud Services Inc.") > 0.8


def _labels() -> dict:
    inv = ExtractedInvoice(
        vendor_name="Nimbus Cloud Services Inc.", invoice_number="INV-1",
        currency="USD", line_items=[LineItem(description="hosting", amount=100.0)],
        subtotal=100.0, tax=0.0, total=100.0,
    )
    return {"invoice": inv.model_dump(),
            "category": {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
                         "level1": "Direct", "level2": "Technology", "level3": "Cloud Infrastructure"}}


def test_score_fixture_perfect_prediction():
    labels = _labels()
    extracted = ExtractedInvoice(**labels["invoice"])
    categorized = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting & Infrastructure",
        level1="Direct", level2="Technology", level3="Cloud Infrastructure",
        confidence=0.9, rationale="r")
    res = score_fixture(labels, extracted, categorized)
    assert res["fields"]["vendor_name"] == 1.0
    assert res["category"]["account_code"] is True
    assert res["category"]["level1"] is True


def test_score_fixture_handles_pipeline_failure():
    res = score_fixture(_labels(), None, None)  # pipeline produced nothing
    assert res["fields"]["vendor_name"] == 0.0
    assert res["category"]["account_code"] is False


def test_score_fixtures_aggregates(tmp_path):
    labels = _labels()
    fdir = tmp_path / "00000"
    fdir.mkdir()
    (fdir / "labels.json").write_text(json.dumps(labels))
    (fdir / "invoice.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "manifest.jsonl").write_text(json.dumps({"id": "00000"}) + "\n")

    def fake_pipeline(pdf_path, buyer_context):
        extracted = ExtractedInvoice(**labels["invoice"])
        categorized = CategorizedInvoice(
            account_code="6010", account_name="Cloud Hosting & Infrastructure",
            level1="Direct", level2="Technology", level3="Cloud Infrastructure",
            confidence=0.9, rationale="r")
        return extracted, categorized

    report = score_fixtures(tmp_path, run_pipeline=fake_pipeline)
    assert report["count"] == 1
    assert report["category_accuracy"]["account_code"] == 1.0
    assert report["field_anls"]["vendor_name"] == 1.0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/synthdata/test_score.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Write minimal implementation**

```python
# src/spend_predictor/synthdata/score.py
"""Benchmark the existing pipeline against synthetic fixtures (ANLS + accuracy)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from anls import anls_score

from ..models import CategorizedInvoice, ExtractedInvoice

_STRING_FIELDS = [
    "vendor_name", "invoice_number", "currency",
    "supplier_country_code", "supplier_vat_number",
    "buyer_country_code", "buyer_vat_number", "invoice_date",
]


def anls_field(pred: str, gold: str) -> float:
    """ANLS similarity for one string field (0..1). Empty gold or pred -> handled by anls."""
    gold = "" if gold is None else str(gold)
    pred = "" if pred is None else str(pred)
    if not gold and not pred:
        return 1.0
    return float(anls_score(prediction=pred, gold_labels=[gold], threshold=0.5))


def score_fixture(
    labels: dict, extracted: ExtractedInvoice | None, categorized: CategorizedInvoice | None
) -> dict:
    """Score one fixture: per-field ANLS + category exact-match booleans."""
    gold_inv = labels["invoice"]
    gold_cat = labels["category"]
    fields: dict[str, float] = {}
    for name in _STRING_FIELDS:
        gold = gold_inv.get(name) or ""
        pred = getattr(extracted, name, None) if extracted else None
        fields[name] = anls_field(pred or "", gold)

    category = {
        key: bool(categorized and getattr(categorized, key) == gold_cat[key])
        for key in ("account_code", "level1", "level2", "level3")
    }
    return {"fields": fields, "category": category}


def _default_run_pipeline(
    pdf_path: str, buyer_context: str
) -> tuple[ExtractedInvoice | None, CategorizedInvoice | None]:  # pragma: no cover - live path
    from ..flow import InvoiceFlow
    from ..rag.indexer import build_index, load_accounts

    build_index()
    flow = InvoiceFlow()
    flow.kickoff(inputs={"pdf_path": pdf_path, "buyer_context": buyer_context,
                         "accounts": load_accounts()})
    return flow.state.extracted, flow.state.categorized


def score_fixtures(fixtures_dir: Path, *, run_pipeline=_default_run_pipeline) -> dict:
    """Run the pipeline over every fixture PDF and aggregate ANLS + accuracy."""
    fixtures_dir = Path(fixtures_dir)
    rows = []
    for fdir in sorted(p for p in fixtures_dir.iterdir() if (p / "labels.json").exists()):
        labels = json.loads((fdir / "labels.json").read_text())
        buyer = labels.get("buyer", {})
        buyer_context = f"{buyer.get('name', '')}: {buyer.get('business_description', '')}"
        try:
            extracted, categorized = run_pipeline(str(fdir / "invoice.pdf"), buyer_context)
        except Exception as exc:  # noqa: BLE001 - a pipeline failure scores as zero, not a crash
            print(f"  pipeline error on {fdir.name}: {exc}")
            extracted, categorized = None, None
        rows.append(score_fixture(labels, extracted, categorized))

    count = len(rows)
    if count == 0:
        return {"count": 0, "field_anls": {}, "category_accuracy": {}}

    field_anls = {
        name: round(sum(r["fields"][name] for r in rows) / count, 4)
        for name in _STRING_FIELDS
    }
    category_accuracy = {
        key: round(sum(1 for r in rows if r["category"][key]) / count, 4)
        for key in ("account_code", "level1", "level2", "level3")
    }
    return {"count": count, "field_anls": field_anls, "category_accuracy": category_accuracy}


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the pipeline against synthetic fixtures.")
    ap.add_argument("--fixtures", type=Path, default=Path("data/synthetic"))
    args = ap.parse_args()
    report = score_fixtures(args.fixtures)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/synthdata/test_score.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/spend_predictor/synthdata/score.py tests/synthdata/test_score.py
git commit -m "feat(synthdata): ANLS + accuracy scorer over the existing pipeline"
```

---

## Task 9: README docs + full suite green

**Files:**
- Modify: `README.md`
- Test: whole suite.

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass (existing suite + new `tests/synthdata/*`).

- [ ] **Step 2: Document the generator + scorer in the README**

Add a "Synthetic data & benchmarking" section to `README.md` covering: the WeasyPrint system-lib apt step; `uv run python -m spend_predictor.synthdata.generate --n 100 --seed 7 --out data/synthetic`; `uv run python -m spend_predictor.synthdata.score --fixtures data/synthetic`; that generation needs the local vLLM up (for descriptions) while scoring runs the full pipeline; and that `data/synthetic/` is gitignored.

```bash
echo "data/synthetic/" >> .gitignore
```

- [ ] **Step 3: Commit**

```bash
git add README.md .gitignore
git commit -m "docs(synthdata): document the generator and ANLS benchmark"
```

---

## Self-Review notes (addressed)

- **Spec coverage:** profiles/level1 (T1), sampler+labels+VAT regimes (T2), LLM enrichment without guided decoding (T3), ERP double-entry (T4), WeasyPrint render (T5), fixture bundle+manifest (T6), orchestrator+CLI (T7), ANLS+accuracy scorer+CLI (T8), docs (T9). Phase 2 intentionally excluded.
- **Ground-truth integrity:** labels originate in the sampler/profiles; `enrich_descriptions` only writes `description` strings and copies all numeric/label fields from the plan (asserted in T3).
- **No guided decoding:** `content._default_generate` returns free text; parsing via `parse_model` (Global Constraints).
- **Type consistency:** `ExtractedInvoice`/`LineItem` reused everywhere; `InvoicePlan`/`LinePlan`, `JournalEntry`, `BuyerProfile`, and the `category` dict shape are consistent across T2–T8.
