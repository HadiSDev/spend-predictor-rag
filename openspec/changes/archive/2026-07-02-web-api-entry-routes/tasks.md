## 1. Schema

- [x] 1.1 Add `ErpEntryRead` to `src/web_api/schemas.py` (id, company_id, erp_integration_id, erp_account_id, source_invoice_id, voucher_id, entry_type, entry_date, debit_amount, credit_amount, currency, erp_entry_id, description, status, account_code, account_name, created_at). Exclude `gt_*` and `raw_json`. `model_config = ConfigDict(from_attributes=True)` like the other Read models

## 2. Router

- [x] 2.1 Create `src/web_api/routers/erp_entries.py` with `APIRouter(prefix="/api/v1", tags=["erp-entries"])`, mirroring `invoice_lines.py`/`invoices.py`
- [x] 2.2 `GET /erp-entries` → `Page[ErpEntryRead]`: `tenant_scope` + `resolve_company_ids`; optional filters `company_id`, `entry_type`, `voucher_id`, `source_invoice_id`, `status`; empty scope → empty page; order by `entry_date DESC, id`; paginate
- [x] 2.3 `GET /erp-entries/{entry_id}` → `ErpEntryRead`: 404 when missing or `company_id` not in `scope.company_ids`

## 3. Wire up

- [x] 3.1 Register the router in `src/web_api/app.py` (`from .routers import ... erp_entries`; `app.include_router(erp_entries.router)`)
- [x] 3.2 Add the entry endpoints to the endpoint list in `CLAUDE.md`

## 4. Tests & verification

- [x] 4.1 `tests/web_api/test_erp_entries.py`: list returns only in-scope entries, paginated with correct `total`
- [x] 4.2 Filters: `source_invoice_id`, `voucher_id`, `entry_type`, `status` each narrow results (AND-composed)
- [x] 4.3 Tenant isolation: a caller cannot see another org's entries (list excludes them; detail returns 404)
- [x] 4.4 Detail: 200 for in-scope id; 404 for unknown id; `gt_*` fields absent from the response
- [x] 4.5 Run `uv run pytest tests/web_api` (and full suite) green
