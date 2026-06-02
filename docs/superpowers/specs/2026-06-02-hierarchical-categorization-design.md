# Hierarchical, Buyer-Aware Spend Categorization — Design

**Date:** 2026-06-02
**Status:** Approved (pending written-spec review)
**Builds on:** `2026-06-01-spend-predictor-rag-design.md`

## 1. Purpose

Replace the flat single `category` with a 4-level spend taxonomy. The top level
(Direct vs Indirect) is **derived from the buyer's business context**, not stored
statically; categorization is informed by **web context** about both the buyer and
the purchased products:

```
Level 1: Direct | Indirect    judged per invoice from BUYER CONTEXT + line items
Level 2: Category             from the chart (e.g. Technology, Travel & Entertainment)
Level 3: Subcategory          from the chart (e.g. Cloud Infrastructure, Lodging)
Level 4: Account              the postable leaf: account_code + account_name (chart)
```

### 1.1 Why L1 is buyer-derived (key principle)

Whether spend is **Direct** (cost of revenue) or **Indirect** (overhead) depends on
**what the buyer does**, not on the product. The same product is Direct for one
buyer and Indirect for another — cloud hosting is Direct/COGS for a SaaS company but
Indirect/overhead for a law firm. Account names do not encode this. So L1 cannot be
a static chart column; it is reasoned per invoice from the buyer's business context
plus the invoice line items. L2/L3/L4 (what the spend *is*) come from the chart
deterministically; only L1 is model-judged.

### 1.2 Two kinds of web context

- **Buyer context** — the buyer's name + website are known beforehand (the backend
  has them). We **scrape the website** (CrewAI keyless `ScrapeWebsiteTool`) once per
  run and summarize it. Drives Direct/Indirect.
- **Product context** — line items can be cryptic (SKUs, terse descriptions). For
  each line item we **web-search** the product (keyless DuckDuckGo) and summarize
  the snippets. Helps the model pick the correct leaf account (and informs L1).

Both are cached and injected into the categorize prompt; both degrade gracefully to
empty context on failure (never fatal).

## 2. End-to-end flow (additions in **bold**)

```
[once per run] resolve BUYER CONTEXT by scraping the buyer's website → cache
per invoice:
PDF → extract (vendor + line items) → verify → RESEARCH PRODUCTS (search each
      line item → product context) → categorize (pick leaf from chart candidates +
      classify Direct/Indirect from buyer + product context & line items)
    → ground (L2/L3/leaf from chart) → ledger
```

`run_all()` resolves the buyer context once and passes it into each invoice flow.

## 3. Chart of accounts schema

`data/chart_of_accounts.csv` — **no `level1`/Direct-Indirect column** (buyer-specific).
Columns:

```
account_code,account_name,level2,level3,description
```

- `account_code` — leaf id; `account_name` — leaf label (the L4 node).
- `level2`, `level3` — category / subcategory (what the spend is).
- `description` — free text for embedding/retrieval.

Sample chart (rebuilt, ~18 accounts; L1 not present):

```csv
account_code,account_name,level2,level3,description
6010,Cloud Hosting & Infrastructure,Technology,Cloud Infrastructure,cloud servers compute storage hosting infrastructure
6015,Third-Party APIs & Data,Technology,APIs & Data,third-party api usage data feeds model inference
6020,Software Subscriptions,Technology,SaaS & Licenses,saas software licenses subscription tools
6030,Telecommunications,Technology,Connectivity,internet phone mobile connectivity services
6500,Office Supplies,Facilities & Office,Office Supplies,stationery paper printer supplies
6510,Office Equipment,Facilities & Office,Equipment,furniture monitors hardware durable equipment
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

## 4. Buyer configuration (`config.py`, `.env.example`)

Buyer is provided beforehand (no invoice extraction):

- `BUYER_NAME` — e.g. `"Acme Analytics, Inc."` (recorded in the ledger).
- `BUYER_WEBSITE` — e.g. `"https://acme.example"` (scraped for context).
- `WEB_CONTEXT_CACHE_DIR` (default `<root>/data/web_cache`, gitignored) — shared by
  buyer and product context.
- `PRODUCT_SEARCH_MAX_RESULTS` (default `3`).

`ExtractedInvoice` is **unchanged** (vendor + line items; no buyer field).

## 5. Web context (`web_context.py`, new)

One module for both external lookups, with shared disk caching (`cache_dir/<slug>.txt`)
and dependency-injected primitives so unit tests run offline.

- `get_buyer_context(name=config.BUYER_NAME, website=config.BUYER_WEBSITE, *,
  scrape_fn=_scrape, summarize_fn=_summarize_buyer, cache_dir=...) -> str`
  - No name+website → `""`. Cache hit → return file. Else `scrape_fn(website)` →
    raw text → `summarize_fn` → 2-3 sentence business note → cache → return.
  - `_scrape(website)` = CrewAI keyless `ScrapeWebsiteTool(website_url=website).run()`,
    called directly in code; any failure → `""`.

- `get_product_context(line_items, vendor_name, *, search_fn=_ddg_search,
  summarize_fn=_summarize_products, cache_dir=...) -> str`
  - **One search per line item** (per §scoping): for each item, query
    `f"{vendor_name} {item.description}"`, cached per-query
    (`search_fn(query) -> list[{title, body, href}]`).
  - Collect each item's top snippets, then `summarize_fn(items_with_snippets)` →
    a compact note: one short line per item describing what the product is. Empty
    results for an item → that line says "no info found".
  - `_ddg_search(query, max_results=config.PRODUCT_SEARCH_MAX_RESULTS)` uses the
    keyless `ddgs` library (`from ddgs import DDGS; DDGS().text(query, max_results=...)`);
    network failure → `[]`.

Both summarizers use `config.get_llm().call(...)`. The per-query search cache means
repeated products across invoices are searched once.

> **Cost/latency note:** per-line-item search adds N web calls per invoice (bounded
> by item count, mitigated by the cache). `run_all` logs how many searches were made.

## 6. Models (`models.py`)

```python
class AccountChoice(BaseModel):
    """Categorizer output: the chosen leaf + the buyer-derived L1."""
    account_code: str
    account_name: str
    level1: Literal["Direct", "Indirect"]   # judged from buyer context + line items
    confidence: float                        # 0..1
    rationale: str

class CategorizedInvoice(BaseModel):
    """Final, hierarchy-enriched categorization."""
    account_code: str
    account_name: str
    level1: str          # from the model (buyer-derived)
    level2: str          # from the chart
    level3: str          # from the chart
    confidence: float
    rationale: str
```

`Literal["Direct","Indirect"]` makes CrewAI enforce a valid L1. `InvoiceState` gains
`buyer_context: str = ""` and `product_context: str = ""`; `categorized` stays
`CategorizedInvoice | None`.

## 7. RAG layer (`rag/indexer.py`)

- `build_index()` embeds each account as
  `"{level2} > {level3} > {account_name}: {description}"` (no L1).
- `retrieve_accounts()` / `load_accounts()` unchanged in signature; metadata dicts
  carry `level2/level3`.

## 8. Flow (`flow.py`)

- `InvoiceState` gains `buyer_context` (from the flow input) and `product_context`.
- New `@listen(verify) research_products` step (skips on skipped/errored): sets
  `state.product_context = get_product_context(state.extracted.line_items,
  state.extracted.vendor_name)`. A search/summarize failure degrades to `""` (not a
  per-invoice error).
- `categorize` (now `@listen(research_products)`):
  1. `candidates = retrieve_accounts(query, top_k=5)`.
  2. Prompt includes: **buyer context**, **product context**, the **invoice line
     items** (description/qty/amount), and candidate leaf accounts (with L2/L3).
  3. `make_categorizer().kickoff(prompt, response_format=AccountChoice)` → leaf +
     Direct/Indirect.
  4. `ground_categorization(choice, candidates, accounts_by_code)` → enriched
     `CategorizedInvoice`.
  Wrapped in the existing per-stage try/except (records `status=error` on failure).
- `record_to_ledger` passes `buyer_name=config.BUYER_NAME`.
- `run_all()`: `build_index()`; `buyer_context = get_buyer_context()` once; per pdf
  `InvoiceFlow().kickoff(inputs={"pdf_path": str(pdf), "buyer_context": buyer_context})`.

## 9. Grounding (`grounding.py`)

`ground_categorization(choice: AccountChoice, candidates, accounts_by_code)
-> tuple[CategorizedInvoice, str]`:

- Valid `account_code`: build `CategorizedInvoice` with `level2/level3/account_name`
  from the chart row and **`level1` carried from `choice`** (buyer-derived).
- Invalid code, candidates exist: snap leaf to `candidates[0]` (its L2/L3/name), keep
  `choice.level1`; note records the snap.
- No candidates: keep the choice's code; blank L2/L3; note. (Rare.)

L1 is never overwritten by the chart; L2/L3/leaf are always chart-grounded.

## 10. Ledger (`ledger.py`)

`LEDGER_COLUMNS` (adds `buyer_name`, replaces `category` with the three levels):

```
source_file, status, invoice_date, vendor_name, buyer_name, invoice_number, total,
currency, level1, level2, level3, account_code, account_name, arithmetic_ok,
confidence, notes
```

`build_ledger_row` gains a `buyer_name` parameter. Processed rows carry `buyer_name`
+ `level1/2/3`; skipped/error rows leave categorization columns blank with the reason
in `notes`.

## 11. Agents (`agents.py`)

- `make_extractor` — unchanged (vendor + line items).
- `make_categorizer` goal/backstory: "choose the best **leaf account** from the
  candidates, and classify the spend as **Direct or Indirect** based on the buyer's
  business context and the invoice line items; do not invent an account code."
  Toolless, `response_format=AccountChoice`.

## 12. Dependencies

- `crewai-tools` — for `ScrapeWebsiteTool` (buyer website scrape).
- `ddgs` — keyless DuckDuckGo search (product lookups).

## 13. Testing

- `web_context` — buyer: cache miss calls scrape+summarize and writes cache, cache
  hit skips both, missing name+website → `""`, scrape `""` → minimal note. product:
  one `search_fn` call per line item, summarize once, cache hit skips, empty results
  → "no info" lines. All via injected fakes (offline).
- `models` — `AccountChoice` rejects an L1 outside {Direct,Indirect}.
- `indexer` — chart helper uses `level2/level3`; `retrieve_accounts` rows carry them.
- `grounding` — valid → L2/L3 from chart, L1 from choice; invalid → snap L2/L3, keep
  choice L1; empty candidates → blank L2/L3.
- `ledger` — new columns/order; processed has buyer_name + levels; skipped/error blank.
- `flow` — offline fakes for `extract`, `get_product_context`,
  `retrieve_accounts`/`load_accounts`, and the categorizer (`AccountChoice`); kickoff
  with a `buyer_context` input; assert the ledger row carries `buyer_name`, `level1`
  (choice), `level2/level3` (chart).

## 14. Out of scope (YAGNI)

- Variable-depth taxonomies (fixed at 4 levels).
- Per-invoice / multi-buyer resolution (single configured buyer; cache already keyed
  by buyer, so extendable).
- Per-level confidence; scheduled cache refresh (manual clear).
