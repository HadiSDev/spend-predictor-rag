## Why

The sync pipeline pulls raw GL postings from ERP connectors into `ErpEntry`, but
nothing in the product shows them. The only place they surface is aggregated
totals on the dashboard, so a user who runs a sync has no way to see what
actually landed, spot entries that failed, or trace a supplier charge back to its
postings.

The sidebar reserves that slot for an "Invoices" page, but the invoice is the
wrong unit to lead with: one spend event is several entries (net, VAT, payable),
and the invoice layer is a derived, categorization-focused view built on top of
them. Entries are what the ERP actually gave us, so that is what the page should
show.

## What Changes

- Replace the disabled **Invoices** sidebar entry with an enabled **Entries**
  entry pointing at a new `/entries` route. No invoice page is added or removed —
  there was never one — and the invoice domain model, its API, and the
  categorization lifecycle are untouched.
- Add an **Entries page** that lists synced ERP data **grouped by voucher**:
  one collapsed row per voucher showing supplier, date, entry count and totals,
  expandable to reveal the individual postings underneath.
- Filters on the page: **company**, **date range** (`accounting_date`),
  **entry type**, **status**, and **supplier**. Filter state lives in the URL so a
  filtered view is linkable and survives reload.
- Clicking an entry opens a **side drawer** with its full detail from
  `GET /api/v1/erp-entries/{id}` — account, voucher, source invoice, currency,
  amounts, status, error message, and the ERP's own identifiers.
- Add `GET /api/v1/erp-entries/vouchers`: a **voucher-grouped, paginated** list.
  Pagination is over vouchers, not entries, so a voucher's postings are never
  split across a page boundary. Entries with no `voucher_id` form a group of one.
- Extend `GET /api/v1/erp-entries` with `from`/`to` (on `accounting_date`) and
  `vendor_id` filters. `vendor_id` resolves through the entry's source invoice,
  since entries carry no vendor of their own. The reports endpoints already
  accept `from`/`to`, so the parameter names stay consistent across the API.
- Enrich `ErpEntryRead` with the account's `erp_account_code` /
  `erp_account_name` and the source invoice's `vendor_id` / `vendor_name`, so a
  row can be rendered without the client resolving three ids by hand. Additive
  only — no existing field changes or disappears.

## Capabilities

### New Capabilities

- `frontend-erp-entries`: the Entries page — voucher-grouped listing of synced
  ERP data, URL-backed filters, expandable voucher rows, entry detail drawer,
  and its loading, empty, and error states.

### Modified Capabilities

- `web-api-entry-review`: adds the voucher-grouped list endpoint; adds
  `from`/`to` and `vendor_id` filters to the entry list; adds denormalized
  account and vendor fields to the entry read model.
- `frontend-auth-dashboard`: the application-shell requirement currently expects
  the Invoices navigation entry to be a disabled placeholder; it becomes an
  enabled Entries link to a real route.
- `frontend-ui-library`: the component set gains a **Drawer** (side-anchored
  panel), which the library does not yet provide and the entry detail needs.

## Impact

**Backend** (`src/web_api/`)

- `routers/erp_entries.py` — new `/erp-entries/vouchers` endpoint (must be
  declared before `/erp-entries/{entry_id}` so the literal path wins), new
  `from`/`to`/`vendor_id` filters on the list endpoint.
- `schemas.py` — `ErpEntryRead` gains four denormalized read-only fields; new
  `VoucherGroupRead`.
- No migration: every field involved already exists; the additions are joins in
  the read path.

**Frontend** (`frontend/src/`)

- New `routes/_authed/entries.tsx` and `components/entries/` (voucher table,
  filter bar, detail drawer).
- New `components/ui/drawer.tsx`, exported from the `ui/` barrel and added to the
  `/ui` kitchen-sink route.
- New `lib/entries.ts` query module; `lib/types.ts` gains the entry, voucher
  group, and filter types.
- `components/app-shell.tsx` — `NAV_ITEMS` swaps Invoices for Entries.
- Reuses the existing vendor list (`GET /vendors`, already `q`-searchable) for
  the supplier filter, and the companies list for the company filter.

**Not in scope**

- No invoice or invoice-line review UI, and no change to how entries are synced,
  categorized, or aggregated. The page is read-only.
