## Why

The web API exposes raw, row-level data (invoices, lines, entries) but no
rolled-up numbers, so the dashboard and any customer report has to pull every
row and sum client-side. Enterprises reviewing their spend need server-computed
aggregates — total debits/credits, invoice-line totals, spend per category and
per vendor, and the categorization funnel — scoped to their organization.

## What Changes

- Add a **reporting controller** to `web_api`: read-only aggregate endpoints
  under `/api/v1/reports/*`, tenant-scoped like the existing read endpoints.
- Add a pure aggregation **service** (`web_api/reporting.py`) that computes the
  rollups with SQL `GROUP BY` (no per-row Python summation).
- **Ledger sums are entry-based** (`ErpEntry` is the financial source of truth):
  - `GET /reports/entries-summary` — sum of debits/credits (+ net, count) grouped
    by `entry_type`, split by currency; optional `entry_type` and date-range
    filters.
  - `GET /reports/entries-by-account` — the same sums grouped by ERP account
    (code, name, type), split by currency.
- **Category & vendor breakdowns** come from the invoice/line layer, where those
  dimensions actually live (entries carry no spend category or vendor, and
  summing raw entries per vendor would double-count net + VAT + AP):
  - `GET /reports/spend-by-category` — sum of categorized invoice-line amounts +
    counts grouped by `level_2` (optionally `level_3`), split by currency.
  - `GET /reports/spend-by-vendor` — sum of invoice totals + counts grouped by
    vendor (with vendor name), split by currency.
- All endpoints accept an optional `company_id` (validated against the caller's
  scope) and an optional `from`/`to` date range; monetary sums are grouped by
  currency rather than added across currencies.
- Reporting lives in `web_api` (the customer domain); it does **not** reuse the
  `ai_api/aggregation` stub, which stays the AI pipeline's internal analytics
  (`web_api` never imports `ai_api`).

## Capabilities

### New Capabilities
- `web-api-reporting`: read-only, tenant-scoped aggregate reporting endpoints
  over the domain data (entry sums, invoice-line sums, spend per category, spend
  per vendor, categorization funnel), grouped by currency.

### Modified Capabilities

## Impact

- New `web_api/reporting.py` (aggregation queries) and
  `web_api/routers/reports.py` (endpoints), registered in `web_api/app.py`.
- New Pydantic response schemas in `web_api/schemas.py`.
- Reuses `deps.tenant_scope` / `resolve_company_ids`; no new auth surface, no DB
  migration (read-only over existing tables).
- **Depends on** `erp-entry-model-cleanup` for `ErpEntry.accounting_date` (the
  date axis for entry reports).
- Docs: `CLAUDE.md` endpoint list.
