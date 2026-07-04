## Context

`web_api` serves row-level reads (invoices, invoice-lines, erp-entries) behind
Clerk auth, with a `tenant_scope` dependency that yields the caller's
`company_ids` and `resolve_company_ids` to validate a client-supplied
`company_id`. The financial source of truth is `ErpEntry`
(`debit_amount`/`credit_amount`/`entry_type`/`currency`/`accounting_date`, linked
to `ErpAccount` and, for purchase invoices, to an `Invoice` via
`source_invoice_id`). Category and vendor dimensions live on the invoice/line
layer: `InvoiceLine` (`amount`/`level_2`/`level_3`/`status`) and `Invoice`
(`total`/`currency`/`vendor_id`). There is a separate `ai_api/aggregation` stub,
but `web_api` cannot import `ai_api`, so customer reporting is built here.

Depends on **erp-entry-model-cleanup** for the `accounting_date` field (the
date axis for entry reports).

## Goals / Non-Goals

**Goals:**
- Server-computed aggregates: entry debit/credit sums by type and by account
  (the ledger truth), plus spend by category and by vendor for the review UI.
- Correct multi-tenant scoping (never cross the caller's org boundary) and
  correct money handling (never sum different currencies together).
- Pure SQL `GROUP BY`; response size is O(groups), not O(rows).

**Non-Goals:**
- Time-series/trend buckets, redundancy, and savings (separate workstreams).
- Cross-currency conversion / FX normalization.
- Caching / materialized views (revisit if slow).
- Reusing or filling the `ai_api/aggregation` stub (different consumer, blocked
  by the import direction).

## Decisions

### Reporting lives in `web_api`, as a service + router
`web_api/reporting.py` holds pure functions
`(session, company_ids, filters) -> list[rows]` using `func.sum`/`func.count` +
`group_by`; `web_api/routers/reports.py` exposes them as `GET /api/v1/reports/*`.
The router does auth/scoping/shape; the service does SQL. Mirrors the existing
router style and keeps aggregation unit-testable without HTTP.

### Ledger sums are entry-based; category/vendor come from the invoice layer
`ErpEntry` is the authoritative financial record, so the money totals
(`entries-summary`, `entries-by-account`) aggregate entries directly. Entries
carry **no spend category** (they are never categorized) and **no vendor**, and
`SpendCategory` has no ERP-account bridge — so category and vendor spend are
computed from the invoice/line layer where those dimensions are modeled. Summing
raw entries per vendor would also double-count (net + VAT + AP postings), which
invoice totals avoid.

### Tenant scoping reuses the existing chain
Endpoints depend on `tenant_scope` (any authenticated role may read, consistent
with the other read endpoints) and resolve the company set via
`resolve_company_ids(scope, company_id)` — a foreign `company_id` is a 404, an
empty scope yields empty rows. Every query filters `company_id IN (company_ids)`.

### Group money by currency, never sum across it
Every monetary rollup includes `currency` in its `GROUP BY` and in the response
rows; callers get one row per (dimension, currency). Amounts are `Decimal`;
`func.sum` over an all-NULL group is coalesced to 0 so responses are numeric.

### Dimensions and sources
- **entries-summary** — from `ErpEntry`, group by `(entry_type, currency)`;
  return `sum(debit_amount)`, `sum(credit_amount)`, `net = debits − credits`,
  `count`. Optional `entry_type` filter and `from`/`to` on `accounting_date`.
- **entries-by-account** — from `ErpEntry` joined to `ErpAccount`, group by
  `(erp_account_id, erp_account_code, erp_account_name, currency)`; same sums +
  `count`. Same optional filters.
- **spend-by-category** — from `InvoiceLine` where `status IN (ai_categorized,
  verified)`, joined to `Invoice` for currency, group by `(level_2[, level_3],
  currency)`; return `sum(amount)`, `count`. A `level` param picks `level_2`
  vs `level_2`+`level_3` (default `level_2`). Date range on `Invoice.invoice_date`.
- **spend-by-vendor** — from `Invoice` joined to `Vendor`, group by
  `(vendor_id, vendor_name, currency)`; return `sum(total)`, `count`. Date range
  on `Invoice.invoice_date`.

### Response shape
Each endpoint returns a small envelope `{ rows: [...] }` (not the paginated
`Page` — aggregates are already small). Each row carries its grouping keys + the
aggregates, ordered deterministically (descending primary total, then key).

## Risks / Trade-offs

- **Category/vendor not entry-derived** → intentional; entries lack those
  dimensions and vendor-via-entries double-counts. Documented in the contract.
- **Line/vendor currency via a join** to `Invoice` (lines store no currency) →
  cheap and keeps money grouped correctly.
- **NULL amounts** → `func.sum` ignores NULLs; coalesce group results to 0.
- **Mixed-currency orgs** → multiple rows per dimension; correct but callers must
  handle >1 currency (documented).
- **No pagination on aggregates** → fine while dimensions are bounded; revisit
  for tenants with very large vendor sets.
