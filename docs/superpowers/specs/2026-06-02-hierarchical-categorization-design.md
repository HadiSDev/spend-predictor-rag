# Hierarchical Spend Categorization — Design

**Date:** 2026-06-02
**Status:** Approved (pending written-spec review)
**Builds on:** `2026-06-01-spend-predictor-rag-design.md`

## 1. Purpose

Replace the flat single `category` with a 4-level spend taxonomy:

```
Level 1: Direct | Indirect          (cost of revenue vs overhead)
Level 2: Category                    (e.g. Technology, Travel & Entertainment)
Level 3: Subcategory                 (e.g. Cloud Infrastructure, Lodging)
Level 4: Account                     (the postable leaf: account_code + account_name)
```

The model picks only the **leaf account**; levels 1–3 are derived deterministically
from the chosen chart row, so the Direct/Indirect classification and the rest of the
path are always internally consistent and never hallucinated.

## 2. Chart of accounts schema

`data/chart_of_accounts.csv` columns (replaces the old `category` column):

```
account_code,account_name,level1,level2,level3,description
```

- `account_code` — leaf id. Convention: Direct → `5xxx` (cost of revenue), Indirect
  → `6xxx`/`7xxx` (operating expense).
- `account_name` — leaf label (the L4 node).
- `level1` — exactly `Direct` or `Indirect`.
- `level2`, `level3` — category / subcategory.
- `description` — free text used for embedding/retrieval.

Sample chart (rebuilt, ~18 accounts, both branches populated). Illustrative
classification — replaceable with the user's real chart:

```csv
account_code,account_name,level1,level2,level3,description
5010,Cloud Hosting & Infrastructure,Direct,Technology,Cloud Infrastructure,cloud servers compute storage hosting infrastructure
5020,Third-Party APIs & Data,Direct,Technology,APIs & Data,third-party api usage data feeds model inference
5030,Contractor - Delivery,Direct,People,Contract Labor,contractors freelancers billable project delivery
5040,Payment Processing Fees,Direct,Financial,Merchant Fees,payment gateway card processing transaction fees
5050,Shipping & Freight,Direct,Fulfillment,Shipping,courier postage freight delivery
6020,Software Subscriptions,Indirect,Technology,SaaS & Licenses,saas software licenses subscription tools
6030,Telecommunications,Indirect,Technology,Connectivity,internet phone mobile connectivity services
6500,Office Supplies,Indirect,Facilities & Office,Office Supplies,stationery paper printer supplies
6510,Office Equipment,Indirect,Facilities & Office,Equipment,furniture monitors hardware durable equipment
6610,Legal Fees,Indirect,Professional Services,Legal,legal counsel attorney compliance services
6620,Accounting & Audit,Indirect,Professional Services,Accounting,accounting bookkeeping audit tax services
6700,Marketing & Advertising,Indirect,Sales & Marketing,Advertising,advertising campaigns promotion marketing
6800,Travel - Airfare,Indirect,Travel & Entertainment,Airfare,flights airline tickets business travel
6810,Travel - Lodging,Indirect,Travel & Entertainment,Lodging,hotels accommodation business travel
6820,Meals & Entertainment,Indirect,Travel & Entertainment,Meals,business meals client entertainment catering
6900,Utilities,Indirect,Facilities & Office,Utilities,electricity water gas facility utilities
6910,Rent & Lease,Indirect,Facilities & Office,Rent & Lease,office rent equipment lease payments
7100,Training & Development,Indirect,People,Training,courses conferences training employee development
```

## 3. Models (`models.py`)

Split the LLM output from the enriched final record:

```python
class AccountChoice(BaseModel):
    """The categorizer's pick — a single leaf account only."""
    account_code: str
    account_name: str
    confidence: float          # 0..1
    rationale: str

class CategorizedInvoice(BaseModel):
    """Final, hierarchy-enriched categorization (levels filled from the chart)."""
    account_code: str
    account_name: str
    level1: str                # Direct | Indirect
    level2: str
    level3: str
    confidence: float
    rationale: str
```

`InvoiceState.categorized` becomes `CategorizedInvoice | None` (unchanged field
name; richer type). The categorize step's `response_format` is `AccountChoice`.

## 4. RAG layer (`rag/indexer.py`)

- `build_index()` embeds each account as
  `"{level1} > {level2} > {level3} > {account_name}: {description}"` so retrieval
  is hierarchy-aware. (Idempotency is still count-based.)
- `retrieve_accounts()` / `load_accounts()` are unchanged in signature; their
  returned metadata dicts now include `level1/level2/level3`.

## 5. Grounding (`grounding.py`)

`ground_categorization(choice: AccountChoice, candidates, accounts_by_code)
-> tuple[CategorizedInvoice, str]`:

- If `choice.account_code` is in `accounts_by_code`: build a `CategorizedInvoice`
  from that chart row's `level1/level2/level3/account_name` plus the choice's
  `confidence`/`rationale`. Note `""`.
- Else if candidates exist: snap to `candidates[0]`, building the
  `CategorizedInvoice` from that row's full hierarchy; note records the
  correction (`"... invalid code 'X'; snapped to 'Y'"`).
- Else: return a `CategorizedInvoice` carrying the model's (unvalidated) code with
  blank levels and a note. (Rare: index not built; `run_all` builds it first.)

Levels always come from the chart, so Direct/Indirect is never the model's guess.

## 6. Flow (`flow.py`)

`categorize` step:
1. Build the query (vendor + line-item descriptions).
2. `candidates = retrieve_accounts(query, top_k=5)`.
3. Render candidate lines including the path, e.g.
   `- 5010 | Direct > Technology > Cloud Infrastructure > Cloud Hosting & Infrastructure | cloud servers ...`.
4. `make_categorizer().kickoff(prompt, response_format=AccountChoice)`.
5. `ground_categorization(...)` → enriched `CategorizedInvoice` + note.

Stage error handling and skip propagation are unchanged.

## 7. Ledger (`ledger.py`)

`LEDGER_COLUMNS` replaces `category` with the three levels:

```
source_file, status, invoice_date, vendor_name, invoice_number, total, currency,
level1, level2, level3, account_code, account_name, arithmetic_ok, confidence, notes
```

`build_ledger_row` populates `level1/level2/level3` from the categorized record on
processed rows; blank on skipped/error rows.

## 8. Agents (`agents.py`)

`make_categorizer` goal/backstory updated: "choose the single best **leaf account**
from the provided candidates; do not invent a code or classify the hierarchy
yourself." Still toolless, `response_format=AccountChoice`.

## 9. Testing

- `indexer` — `_write_coa` test helper gains level columns; assert
  `retrieve_accounts` returns rows carrying `level1/2/3`.
- `grounding` — valid code → enriched levels from chart; invalid code → snap with
  the snapped account's full path (assert `level1` flips to the candidate's, e.g.
  Direct); empty candidates → blank levels + note.
- `ledger` — new columns present and ordered; processed row carries levels; skipped
  and error rows have blank levels.
- `flow` — fakes return an `AccountChoice`; assert the ledger row has the derived
  `level1/level2/level3` (offline, via monkeypatched `retrieve_accounts`/`load_accounts`).

## 10. Out of scope (YAGNI)

- Variable-depth taxonomies (we fix at 4 levels).
- Per-level confidence (single confidence on the leaf pick).
- Reclassifying Direct/Indirect by business model at runtime (encoded in the chart).
