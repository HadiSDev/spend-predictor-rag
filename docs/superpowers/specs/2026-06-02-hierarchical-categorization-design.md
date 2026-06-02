# Hierarchical, Buyer-Aware Spend Categorization — Design

**Date:** 2026-06-02
**Status:** Approved (pending written-spec review)
**Builds on:** `2026-06-01-spend-predictor-rag-design.md`

## 1. Purpose

Replace the flat single `category` with a 4-level spend taxonomy, where the top
level (Direct vs Indirect) is **derived from the buyer's business context**, not
stored statically:

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

### 1.2 Buyer info is known beforehand

The backend already knows the buyer (the company whose spend we categorize) — its
**name and website**. We therefore do **not** extract the buyer from the invoice or
search by name. The buyer's name + website are supplied as configuration, and we
derive business context by **scraping the website** (cached). The bundled default
represents one example buyer; swap the config to categorize for a different buyer.

## 2. End-to-end flow (additions in **bold**)

```
[once per run] resolve BUYER CONTEXT by scraping the buyer's website → cache
per invoice:
PDF → extract (vendor + line items) → verify
    → categorize (pick leaf from chart candidates + classify Direct/Indirect from
      buyer context & line items) → ground (L2/L3/leaf from chart) → ledger
```

`run_all()` resolves the buyer context once and passes it into each invoice flow.

## 3. Chart of accounts schema

`data/chart_of_accounts.csv` — **no `level1`/Direct-Indirect column** (that is
buyer-specific). Columns:

```
account_code,account_name,level2,level3,description
```

- `account_code` — leaf id; `account_name` — leaf label (the L4 node).
- `level2`, `level3` — category / subcategory (what the spend is).
- `description` — free text for embedding/retrieval.

Sample chart (rebuilt, ~18 accounts). L1 is *not* present here:

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

The buyer is provided beforehand (no invoice extraction):

- `BUYER_NAME` — e.g. `"Acme Analytics, Inc."` (recorded in the ledger).
- `BUYER_WEBSITE` — e.g. `"https://acme.example"` (scraped for context).
- `BUYER_CACHE_DIR` (default `<root>/data/buyer_cache`, gitignored).

Existing vLLM/embedding/path settings unchanged. `ExtractedInvoice` is **unchanged**
(still vendor + line items; no buyer field).

## 5. Buyer context resolution (`buyer_context.py`, new)

Turns the buyer's website into a short business-context note used to judge
Direct/Indirect.

- `get_buyer_context(name=config.BUYER_NAME, website=config.BUYER_WEBSITE, *,
  scrape_fn=_scrape, summarize_fn=_llm_summarize, cache_dir=config.BUYER_CACHE_DIR) -> str`
  1. If neither name nor website is set → return `""`.
  2. Cache lookup: `cache_dir/<slug(name or website)>.txt`; if present, return it
     (no network, no LLM).
  3. Else `text = scrape_fn(website)` (raw site text).
  4. `summarize_fn(name, text)` → 2-3 sentence business-context note (industry, what
     they make/sell, how they earn revenue).
  5. Write the note to cache and return it.
- `_scrape(website)` — CrewAI keyless `ScrapeWebsiteTool(website_url=website).run()`
  (from `crewai_tools`), called directly in code (not via LLM tool-calling). On any
  failure returns `""` (degrade gracefully).
- `_llm_summarize(name, text)` — one `config.get_llm().call(...)`; if `text` is
  empty, return a minimal note `"No website context available for '<name>'."`.

`scrape_fn`/`summarize_fn` are injectable so unit tests run offline. Adds the
`crewai-tools` dependency. Cache dir is gitignored.

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

`Literal["Direct","Indirect"]` makes CrewAI enforce a valid L1. `InvoiceState`
gains `buyer_context: str = ""` (populated from the flow input); `categorized`
stays `CategorizedInvoice | None`.

## 7. RAG layer (`rag/indexer.py`)

- `build_index()` embeds each account as
  `"{level2} > {level3} > {account_name}: {description}"` (no L1).
- `retrieve_accounts()` / `load_accounts()` unchanged in signature; metadata dicts
  carry `level2/level3`.

## 8. Flow (`flow.py`)

- `InvoiceState` gains `buyer_context: str = ""`, set via
  `kickoff(inputs={"pdf_path": ..., "buyer_context": ...})`.
- `categorize` step (unchanged position: `@listen(verify)`):
  1. `candidates = retrieve_accounts(query, top_k=5)`.
  2. Prompt includes the **buyer context**, the **invoice line items**
     (description / qty / amount), and the candidate leaf accounts (with L2/L3).
  3. `make_categorizer().kickoff(prompt, response_format=AccountChoice)` → leaf +
     Direct/Indirect.
  4. `ground_categorization(choice, candidates, accounts_by_code)` → enriched
     `CategorizedInvoice`.
  Wrapped in the existing per-stage try/except (records `status=error` on failure).
- `record_to_ledger` passes `buyer_name=config.BUYER_NAME` through to the row.
- `run_all()`: `build_index()`, then `buyer_context = get_buyer_context()` once,
  then per pdf `InvoiceFlow().kickoff(inputs={"pdf_path": str(pdf), "buyer_context": buyer_context})`.
  Buyer-context resolution failures degrade to `""` (not a per-invoice error).

## 9. Grounding (`grounding.py`)

`ground_categorization(choice: AccountChoice, candidates, accounts_by_code)
-> tuple[CategorizedInvoice, str]`:

- Valid `account_code`: build `CategorizedInvoice` with `level2/level3/account_name`
  from the chart row and **`level1` carried from `choice`** (buyer-derived);
  `confidence`/`rationale` from the choice. Note `""`.
- Invalid code, candidates exist: snap leaf to `candidates[0]` (its L2/L3/name),
  keep `choice.level1`; note records the snap.
- No candidates: keep the choice's (unvalidated) code; blank L2/L3; note. (Rare.)

L1 is never overwritten by the chart; L2/L3/leaf are always chart-grounded.

## 10. Ledger (`ledger.py`)

`LEDGER_COLUMNS` (adds `buyer_name`, replaces `category` with the three levels):

```
source_file, status, invoice_date, vendor_name, buyer_name, invoice_number, total,
currency, level1, level2, level3, account_code, account_name, arithmetic_ok,
confidence, notes
```

`build_ledger_row` gains a `buyer_name` parameter. Processed rows carry
`buyer_name` + `level1/2/3`; skipped/error rows leave the categorization columns
blank with the reason in `notes` (buyer_name may still be filled).

## 11. Agents (`agents.py`)

- `make_extractor` — unchanged (vendor + line items).
- `make_categorizer` goal/backstory: "choose the best **leaf account** from the
  candidates, and classify the spend as **Direct or Indirect** based on the buyer's
  business context and the invoice line items; do not invent an account code."
  Toolless, `response_format=AccountChoice`.

## 12. Testing

- `buyer_context` — cache miss calls `scrape_fn`+`summarize_fn` and writes cache;
  cache hit returns file contents without calling either; missing name+website →
  `""`; scrape returning `""` → minimal note. All via injected fakes (offline).
- `models` — `AccountChoice` rejects an L1 outside {Direct,Indirect}.
- `indexer` — chart helper uses `level2/level3`; `retrieve_accounts` rows carry
  them; build_index doc-text format.
- `grounding` — valid code → L2/L3 from chart, L1 from choice; invalid → snap L2/L3,
  keep choice L1; empty candidates → blank L2/L3.
- `ledger` — new columns/order; processed row has buyer_name + levels;
  skipped/error blank.
- `flow` — offline fakes for `extract`, `retrieve_accounts`/`load_accounts`, and the
  categorizer (`AccountChoice`); kickoff with a `buyer_context` input; assert the
  ledger row carries `buyer_name` (config), `level1` (from choice), `level2/level3`
  (from chart).

## 13. Out of scope (YAGNI)

- Variable-depth taxonomies (fixed at 4 levels).
- Per-invoice / multi-buyer resolution (single configured buyer for now; the cache
  is already keyed by buyer so this can extend later).
- Per-level confidence; scheduled refresh of cached buyer context (manual clear).
