## 1. Aggregation service

- [x] 1.1 Add `web_api/reporting.py` with pure functions taking
  `(session, company_ids, *, from_date, to_date, ...)` and returning row dicts,
  using `func.sum`/`func.count` + `group_by`, coalescing sums to 0
- [x] 1.2 `entries_summary` — group `ErpEntry` by `(entry_type, currency)`;
  debits, credits, net, count; optional `entry_type` + `accounting_date` range
- [x] 1.3 `entries_by_account` — join `ErpEntry → ErpAccount`, group by
  `(erp_account_id, code, name, currency)`; same aggregates + filters
- [x] 1.4 `spend_by_category` — `InvoiceLine` (status in `ai_categorized`,
  `verified`) joined to `Invoice` for currency; group by `(level_2[, level_3],
  currency)`; sum(amount), count; `level` granularity; invoice-date range
- [x] 1.5 `spend_by_vendor` — `Invoice` joined to `Vendor`; group by
  `(vendor_id, vendor_name, currency)`; sum(total), count; invoice-date range

## 2. Schemas & router

- [x] 2.1 Add response schemas in `schemas.py` (row models + `{rows: [...]}`
  envelopes) for the four reports
- [x] 2.2 Add `web_api/routers/reports.py` (`prefix=/api/v1`, tag `reports`) with
  the four `GET /reports/*` endpoints: `tenant_scope` + `resolve_company_ids`,
  optional `company_id`/`entry_type`/`from`/`to`/`level` query params
- [x] 2.3 Register the router in `web_api/app.py`

## 3. Tests

- [x] 3.1 `tests/web_api/test_reports.py`: seed entries/lines/invoices/vendors
  across two orgs; assert org scoping + foreign `company_id` → 404 + empty scope
- [x] 3.2 entries-summary/by-account: debit/credit/net/count correct; currencies
  not combined; `entry_type` and `accounting_date` range filters
- [x] 3.3 spend-by-category: only `ai_categorized`/`verified` lines counted;
  `level_2` vs `level_2`+`level_3` granularity
- [x] 3.4 spend-by-vendor: totals + count per vendor with name; date range
- [x] 3.5 `uv run pytest` — full suite green

## 4. Docs

- [x] 4.1 `CLAUDE.md`: add the `/reports/*` endpoints and note reporting lives in
  `web_api` (entry-based ledger sums; category/vendor from the invoice layer)
