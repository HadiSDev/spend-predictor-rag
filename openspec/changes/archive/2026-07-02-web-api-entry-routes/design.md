## Context

The web API (`src/web_api/`) is a Clerk-authenticated resource server exposing
read endpoints for companies, invoices, and invoice-lines. Each read router
follows one pattern: a `tenant_scope` dependency yields the caller's in-scope
`company_ids`, `resolve_company_ids(scope, company_id)` narrows to an optional
requested company, queries filter on `company_id IN (...)`, and results come back
as `Page[T]`. Detail endpoints 404 when the row is missing or out of scope.

The sync pipeline persists `ErpEntry` rows, but no router reads them. This change
adds the entry read surface, reusing the existing deps and pagination.

## Goals / Non-Goals

**Goals:**
- `GET /api/v1/erp-entries` (list + filters + pagination) and
  `GET /api/v1/erp-entries/{id}` (detail), tenant-scoped and read-only.
- An `ErpEntryRead` schema exposing the financial fields, excluding `gt_*`.

**Non-Goals:**
- No writes/mutations — entries are synced from the ERP, not user-editable.
- No nested `/invoices/{id}/entries` route (covered by the `source_invoice_id`
  filter).
- No changes to auth/authorization, the sync runner, connectors, or the mock ERP.
- No exposure of ground-truth columns.

## Decisions

### D1 — Path is `/api/v1/erp-entries`, not `/entries`
Name the domain entity explicitly and avoid confusion with the mock ERP's
upstream `/api/v1/entries` (a different shape). Consistent with reading the
`ErpEntry` table.
- *Alternative rejected:* `/entries` — ambiguous next to the mock ERP endpoint and
  less descriptive of the domain entity.

### D2 — Mirror the invoice-lines router exactly
New `routers/erp_entries.py` copies the `invoice_lines.py` shape: `tenant_scope` +
`resolve_company_ids`, `company_id IN (...)` conditions, `Page[T]`, deterministic
ordering. Detail mirrors `get_invoice`'s 404-on-out-of-scope.
- *Why:* one consistent pattern across the read surface; minimal new surface area;
  tenant isolation is already proven by the existing routers/tests.

### D3 — Filters: company_id, entry_type, voucher_id, source_invoice_id, status
These are the useful query axes: by tenant/company, by posting type
(purchase_invoice / payment / journal_entry), by voucher (all postings of one
document), by the linked invoice scan, and by processing status. All optional,
AND-composed, like the invoice filters.

### D4 — `ErpEntryRead` excludes `gt_*` and `raw_json`
Expose: `id`, `company_id`, `erp_integration_id`, `erp_account_id`,
`source_invoice_id`, `voucher_id`, `entry_type`, `entry_date`, `debit_amount`,
`credit_amount`, `currency`, `erp_entry_id`, `description`, `status`,
`account_code`, `account_name`, `created_at`. Omit `gt_*` (internal benchmarking)
and `raw_json` (bulky provider payload) from the list surface.
- *Ordering:* `entry_date DESC, id` for a stable, useful default (recent first),
  matching the invoices ordering intent.

## Risks / Trade-offs

- **Cross-tenant leakage** → mitigated by reusing `tenant_scope` +
  `company_id IN (scope.company_ids)` on every query and 404 (not 403) on
  out-of-scope detail; covered by tests mirroring the invoice-review tests.
- **Large result sets** (entries are the highest-volume table) → pagination with a
  `page_size` cap (≤200, as elsewhere) and an indexed `company_id` filter.
- **Filter on `source_invoice_id`/`voucher_id` without an index** → acceptable at
  current scale; add indexes later if entry volume warrants (out of scope here).

## Open Questions

- Should the detail endpoint embed the linked invoice or account (nested read)?
  Kept flat for now (ids only), consistent with invoice-lines; can add an
  `?expand=` later if the dashboard needs it.
