## 1. Entry read model carries account and supplier

- [x] 1.1 In `src/web_api/schemas.py`, add `erp_account_code`, `erp_account_name`, `vendor_id`, `vendor_name` to `ErpEntryRead` (all read-only; `vendor_*` nullable)
- [x] 1.2 In `routers/erp_entries.py`, add a private `_entry_select()` building the base `select` joined to `ErpAccount` (inner) and left-joined `Invoice` → `Vendor`, and an `_entry_read(row)` helper that constructs `ErpEntryRead` from the joined row — the single construction path for all three endpoints
- [x] 1.3 Rewrite `get_erp_entry` to use `_entry_select()`/`_entry_read()` so the detail payload matches the list payload, keeping the 404-on-out-of-scope behaviour
- [x] 1.4 Rewrite `list_erp_entries` to use `_entry_select()`/`_entry_read()`, leaving its existing filters and ordering unchanged
- [x] 1.5 Tests: an entry's account code/name are returned by both list and detail; `vendor_id`/`vendor_name` are populated for a linked entry and `null` for one with no `source_invoice_id`

## 2. New filters on the flat entry list

- [x] 2.1 Extract `_entry_conditions(company_ids, *, entry_type, voucher_id, source_invoice_id, status, date_from, date_to, vendor_id)` returning the `WHERE` clause list — one place both endpoints build filters from
- [x] 2.2 Add `from`/`to` query params (aliased to `date_from`/`date_to`) filtering `accounting_date` inclusively; entries with a null `accounting_date` must not match a bounded range
- [x] 2.3 Add a `vendor_id` query param resolving through `source_invoice_id IN (SELECT id FROM invoices WHERE vendor_id = ...)`; entries with no source invoice never match
- [x] 2.4 Tests: date range includes both boundaries and excludes null-dated entries; `vendor_id` returns only that supplier's linked entries and excludes unlinked ones; filters compose with the pre-existing ones

## 3. Voucher-grouped listing endpoint

- [x] 3.1 Add `VoucherGroupRead` to `schemas.py`: `voucher_id` (nullable), `company_id`, `accounting_date`, `entry_types: list[str]`, `vendor_id`, `vendor_name`, `currency`, `debit_total`, `credit_total`, `entry_count`, `entries: list[ErpEntryRead]`
- [x] 3.2 Add `GET /api/v1/erp-entries/vouchers` returning `Page[VoucherGroupRead]`, **declared before** `GET /erp-entries/{entry_id}` so the literal path is not swallowed by the parameterized route
- [x] 3.3 Implement query 1: `GROUP BY company_id, <group key>` over `_entry_conditions(...)`, selecting only `max(accounting_date)` (totals are derived from the fetched entries in 3.4, so a group's claim and its listing cannot disagree); order by `max(accounting_date) DESC NULLS LAST` then `voucher_id`; page with `OFFSET`/`LIMIT`; get `total` via `count(*)` over the grouped subquery (no window functions — the test engine is SQLite)
- [x] 3.4 Implement query 2: one `IN` fetch over the page's `(company_id, voucher_id)` keys using `_entry_select()`, then bucket entries into their groups in Python preserving the group order from query 1
- [x] 3.5 Handle null `voucher_id`: each such entry becomes its own single-entry group with `voucher_id: null`, never merged into one bucket
- [x] 3.6 Derive per-group `currency`, `vendor_id`, `vendor_name` only when every entry in the group agrees, else `null`; collect `entry_types` as the sorted distinct set
- [x] 3.7 Return an empty page when the caller has no companies in scope
- [x] 3.8 Tests: three postings on one voucher come back as one group with correct totals; pagination is over groups and never splits a voucher; a null-`voucher_id` entry is its own group; mixed-currency group reports `currency: null`; filters apply before grouping; two orgs sharing a `voucher_id` are not merged and a non-system-admin sees only its own; no-scope caller gets an empty page
- [x] 3.9 Test the null-`accounting_date` ordering explicitly (must sort last) so the SQLite/Postgres `NULLS` difference cannot regress unnoticed

## 4. Drawer primitive in the UI library

- [x] 4.1 Add `frontend/src/components/ui/drawer.tsx` wrapping the Base UI dialog primitive with side anchoring (`side="right" | "left"`), matching the existing `dialog.tsx` structure and tokens
- [x] 4.2 Export the Drawer parts from `components/ui/index.ts`
- [x] 4.3 Render a Drawer example on the `/ui` kitchen-sink route
- [x] 4.4 Test in `ui.test.tsx`: the drawer opens from its side, moves focus inside, and dismisses on escape and via its close control, returning focus to the trigger

## 5. Frontend data layer

- [x] 5.1 Add `ErpEntryRead`, `VoucherGroupRead`, and the entry filter type to `frontend/src/lib/types.ts`, mirroring the API schemas
- [x] 5.2 Add `frontend/src/lib/entries.ts` with `voucherGroupsQueryOptions(api, filters)` (`GET /erp-entries/vouchers`) and `entryQueryOptions(api, id)` (`GET /erp-entries/{id}`), keying the cache off the filter object
- [x] 5.3 Add `vendorsQueryOptions(api, { q })` for the supplier combobox if `lib/` has no vendor query module yet
- [x] 5.4 Tests for the query modules: filters are serialized as query params, unset filters are omitted from the request

## 6. Entries route and filter bar

- [x] 6.1 Add `frontend/src/routes/_authed/entries.tsx` with `staticData: { title: 'Entries' }`; the parsing itself lives in `lib/entry-search.ts` (`validateEntrySearch` + `applyFilterChange`) so it is testable without mounting a router, covering `company_id`, `from`, `to`, `entry_type`, `status`, `vendor_id`, `page` — unset filters omitted, not empty strings
- [x] 6.2 Add `components/entries/filter-bar.tsx`: company `Select` (from `GET /companies`), date range (`DatePicker`), entry type `Select` (options from `GET /reports/entries-summary`), status `Select` (fixed `pending`/`synced`/`failed`), supplier `Combobox` (searchable `GET /vendors`), plus a clear-filters control
- [x] 6.3 Wire filter changes to `navigate({ search })`, resetting `page` to 1 on any filter change
- [x] 6.4 Regenerate `routeTree.gen.ts`
- [x] 6.5 Tests: `entry-search.test.ts` pins the URL contract (every filter parsed, unset filters stay undefined, empty strings and page 1 dropped, filter changes reset the page); `entries-panel.test.tsx` covers the change wiring through the date range and the option lists. Choosing from a `Select` popup is NOT covered — Base UI only hit-tests its first option under jsdom's zero-size layout, so a click on a later option is swallowed; this is an environment limit, documented in the test file

## 7. Voucher table and entry drawer

- [x] 7.1 Add `components/entries/voucher-table.tsx` built on the `Table` primitives (not `DataTable` — pagination is server-side): one row per group with supplier, latest date, entry type(s), posting count, and totals, expandable to its postings showing account code + name, description, debit, credit
- [x] 7.2 Suppress the amount and show a mixed-currencies indication when a group's `currency` is `null`; never render a cross-currency sum
- [x] 7.3 Render a single-entry group with null `voucher_id` as a plain row with no expand affordance
- [x] 7.4 Badge a group row when any of its entries has a failed status, so a broken sync is findable without expanding every voucher
- [x] 7.5 Wire the existing `Pagination` component to the server's page envelope
- [x] 7.6 Add `components/entries/entry-drawer.tsx`: activating a posting opens the Drawer with the full detail from `GET /erp-entries/{id}` — account, voucher, source invoice, supplier, entry type, accounting date, currency, debit/credit, status, error message, ERP entry id — returning focus to the originating row on close
- [x] 7.7 Add loading (skeleton), error, and two distinct empty states: "nothing synced yet" versus "no entries match these filters" with a clear-filters action; when a supplier filter is active, note that postings not linked to an invoice carry no supplier
- [x] 7.8 Tests: groups render with their postings on expand; a voucherless entry has no expand affordance; mixed-currency group shows no summed amount; failed-entry badge appears on the group row; paging issues a new request; the drawer opens with detail, shows a failed entry's error message, and dismisses on escape

## 8. Navigation

- [x] 8.1 In `components/app-shell.tsx`, replace the disabled `Invoices` `NAV_ITEMS` entry with `{ label: 'Entries', icon: <a ledger-appropriate lucide icon>, to: '/entries' }`
- [x] 8.2 Update `app-shell.test.tsx`: Entries is an enabled link, is marked active on `/entries`, and no disabled Invoices entry remains

## 9. Wrap-up

- [x] 9.1 Run `uv run pytest` — all backend tests pass
- [x] 9.2 Run the frontend suite and `tsc --noEmit` — tests pass and types are clean
- [x] 9.3 Update `CLAUDE.md`: add `/erp-entries/vouchers` and the new entry filters to the endpoint list, and note that `ErpEntryRead` carries resolved account and vendor
- [x] 9.4 Verify the page against real synced data (`uv run uvicorn mock_erp.main:app --port 8001`, then `uv run python -m ai_api.sync.runner`) and settle the open question about escalating failed entries on the group row

## 10. Signed Total column (net spend)

Added after review: the table showed a Debit and a Credit column, and a balanced
voucher carries the same figure in both — one number displayed twice.

- [x] 10.1 Add `amount` to `VoucherGroupRead`: signed `debit - credit` over the group's **expense** postings only, so a refund comes out negative with no special-casing
- [x] 10.2 Carry `ErpAccount.erp_account_type` through `_entry_select()` (the join was already there) and compute `_net_spend(rows)` from it
- [x] 10.3 Return `null` for a voucher with no expense posting (a payment moves money without spending it), and fall back to `debit_total` when the connector declares no account types at all
- [x] 10.4 Tests: net excludes VAT and the payable; `debit_total - credit_total` is provably zero on the same voucher; a refund is negative; a payment has no amount; the no-types fallback holds
- [x] 10.5 Frontend: replace the group row's Debit and Credit columns with one signed **Total**; tint negatives; render `—` rather than `0.00` for a voucher that spent nothing
- [x] 10.6 Keep debit/credit on the expanded postings, where they are the ledger's actual content rather than a summary
- [x] 10.7 Tests: one Total column and no Debit/Credit headers; net shown rather than gross; a refund renders negative; a no-spend voucher shows no figure
- [x] 10.8 Expose `erp_account_type` on `ErpEntryRead` (already joined, previously discarded), so the frontend can tell spend from ledger plumbing
- [x] 10.9 Fix the unused debit/credit side rendering as `DKK 0.00`: connectors send `0.00`, not null, and `"0.00"` is a truthy string
- [x] 10.10 Tests: no exact `DKK 0.00` anywhere in an expanded voucher; exactly one Spend posting and two Not-spend in the sample voucher
- [x] 10.11 Frontend shows **only spend postings**, each as one signed amount — VAT and the counterparty are retained by the API but not displayed, so the visible rows sum to the Total
- [x] 10.12 Expand only when a voucher has more than one spend posting; make a non-expandable row open its posting's detail so the drawer stays reachable
- [x] 10.13 Tests: a split voucher reveals both expense lines summing to the Total and hides the payable; a single-spend voucher offers no expand and opens detail from the row
