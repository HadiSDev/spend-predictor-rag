## Why

The sync pipeline now persists `ErpEntry` rows (raw GL postings, linked to invoice
scans by voucher), but there is **no way to read them over the API**. The web API
exposes companies, invoices, and invoice-lines, yet entries — the atomic financial
record and the source of truth for reconciliation — are invisible to the
dashboard and any client. We need read routes for entry data, mirroring the
existing invoice/invoice-line surface.

## What Changes

- Add tenant-scoped, read-only **entry endpoints** under `/api/v1`:
  - `GET /api/v1/erp-entries` — paginated list with filters (`company_id`,
    `entry_type`, `voucher_id`, `source_invoice_id`, `status`).
  - `GET /api/v1/erp-entries/{entry_id}` — one entry.
- Add an `ErpEntryRead` response schema exposing the core financial fields
  (account, voucher, source invoice, entry_type, date, debit/credit, currency,
  status). Ground-truth (`gt_*`) columns are **not** exposed (internal
  benchmarking only).
- Register the new router in the app factory.
- Access follows the existing read convention: any authenticated org member can
  read within their tenant scope (system admins across orgs); results are scoped
  by `company_id`.

The path is `erp-entries` (not `entries`) to avoid colliding with the mock ERP's
`/api/v1/entries` shape and to name the domain entity (`ErpEntry`) explicitly.

## Capabilities

### New Capabilities
- `web-api-entry-review`: read endpoints for `ErpEntry` data (list with filters +
  pagination, and single-entry fetch), tenant-scoped like the invoice surface.

### Modified Capabilities
<!-- None. Authorization/auth behavior is unchanged; entries reuse the existing read scope. -->

## Impact

- **Web API** (`src/web_api/`): new `routers/erp_entries.py`; `ErpEntryRead` in
  `schemas.py`; router registration in `app.py`.
- **Docs**: extend the endpoint list in `CLAUDE.md`.
- **Tests**: `tests/web_api/` — list filters/pagination, tenant scoping (no
  cross-tenant leakage), 404 for out-of-scope/unknown ids.
- No DB, connector, sync-runner, or mock-ERP changes. Reuses `get_session`,
  `tenant_scope`, `resolve_company_ids`, and `Page[T]`.
