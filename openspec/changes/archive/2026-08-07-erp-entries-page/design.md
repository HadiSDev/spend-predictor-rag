## Context

`ErpEntry` rows land in Postgres via `ai_api/sync/runner.py` and are already
readable through `GET /api/v1/erp-entries` (tenant-scoped, paginated, filterable
by company / entry type / voucher / source invoice / status). Nothing renders
them. The sidebar's Invoices slot is a disabled placeholder — there is no
invoice page to replace, only a placeholder to repoint.

Constraints that shape the design:

- **`web_api` must not import `ai_api`.** Everything here lives in `web_api`.
- **Entries carry no vendor and no integration id.** Vendor is reachable only
  through `source_invoice_id → Invoice.vendor_id`; the account is reachable
  through `erp_account_id → ErpAccount`.
- **Money is grouped by currency, never summed across currencies** — the rule
  already enforced in `web_api/reporting.py`.
- **Backend tests run on in-memory SQLite** (`tests/web_api/conftest.py`), so
  the queries must avoid Postgres-only constructs (window functions,
  `DISTINCT ON`, lateral joins).
- **`voucher_id` is nullable** and is only unique within a company — the mock
  ERP emits a per-company integer.

## Goals / Non-Goals

**Goals:**

- Show what a sync actually produced, grouped the way an accountant reads it:
  one voucher, several postings.
- Make a filtered view linkable — filter state in the URL, not component state.
- Let a user trace one posting to its account, voucher, source invoice, and
  supplier without leaving the page.
- Surface failed entries (`status`, `error_message`) so a broken sync is visible
  in the product rather than only in the runner's stdout.

**Non-Goals:**

- No invoice or invoice-line review UI, and no categorization surface. Entries
  are never categorized.
- No writes. The page is read-only; nothing here edits, re-syncs, or retries.
- No CSV/export, no saved views, no column customization.
- No change to the sync pipeline, the aggregation stubs, or the reports.

## Decisions

### Group vouchers on the server, and paginate over vouchers

**Decision:** a new `GET /api/v1/erp-entries/vouchers` returns
`Page[VoucherGroupRead]` — a page *of vouchers*, each carrying its full list of
entries.

**Why not group client-side over the flat list?** Because `page_size` would then
cut through the middle of a voucher: the last group on page 1 would show three of
its five postings, and its totals would be wrong. Grouped display and
entry-level pagination are incompatible. Paginating over the group makes the
group the atomic unit, which is what the user chose to see.

**Why a separate endpoint rather than `?group_by=voucher` on the existing one?**
The response shape differs, and FastAPI's `response_model` is fixed per route —
a conditional shape would mean dropping the model or returning a union that
neither the OpenAPI schema nor the generated client can express usefully. The
flat endpoint stays exactly as it is, so existing callers are unaffected.

**Route ordering matters:** `/erp-entries/vouchers` MUST be declared before
`/erp-entries/{entry_id}` in `routers/erp_entries.py`. FastAPI matches in
declaration order, and the parameterized route would otherwise swallow
`vouchers` and 404 on "entry not found".

### Group identity is `(company_id, voucher_id)`, with a singleton fallback

`voucher_id` is unique only within a company, so grouping on it alone would merge
two companies' vouchers in a system admin's cross-org view. The key is the pair.

Entries with `voucher_id IS NULL` are not silently dropped and not lumped into
one giant "no voucher" bucket — each forms a **group of one** keyed by its own
entry id, with `voucher_id: null`. The UI renders those as an ordinary
non-expandable row.

### Two queries, no window functions

1. **Key page** — `GROUP BY company_id, voucher_id` over the filtered set,
   selecting the aggregates (`max(accounting_date)`, `sum(debit)`, `sum(credit)`,
   `count(*)`), ordered by `max(accounting_date) DESC, voucher_id`, with
   `OFFSET`/`LIMIT`. A second `COUNT(*) OVER` would be the Postgres-native way to
   get `total`; instead a plain `SELECT count(*) FROM (grouped subquery)` is used
   because it also runs on SQLite.
2. **Entry page** — one `IN` query fetching every entry whose key is in that
   page, joined out to account and vendor, then bucketed into the groups in
   Python.

Two round-trips, bounded fan-out, no dialect-specific SQL. The alternative —
one query returning entries with group aggregates attached via window functions —
is fewer round-trips but does not run under the test suite's SQLite engine.

### Aggregate fields are only claimed when the group agrees

A voucher's postings *should* share a currency and a supplier, but nothing in the
schema enforces it. Rather than pick the first row's value and present it as the
group's, the group reports:

- `currency`: the shared value, or `null` when the group's entries disagree.
- `vendor_id` / `vendor_name`: the shared vendor, or `null` when they disagree or
  no entry has a source invoice.
- `entry_types`: the sorted list of distinct types, not a single "leading" type.
  The UI shows the first and a `+N` affordance.
- `debit_total` / `credit_total`: summed. **Only meaningful when `currency` is
  non-null** — the UI suppresses the amount and shows "mixed currencies" when it
  is null, so the page never displays a number that added kroner to euros.

### Denormalize account and vendor onto `ErpEntryRead`

`ErpEntryRead` gains `erp_account_code`, `erp_account_name`, `vendor_id`,
`vendor_name`. Additive and read-only; no existing field changes.

**Why not resolve client-side?** The client would need the account catalog for
every integration plus the vendor list, then join three ids per row in the
browser — three extra requests to render one table, and the account catalog is
only exposed per-integration (`/erp-integrations/{id}/accounts`), so a page
spanning companies would need one request per integration.

The join is `ErpAccount` (inner — `erp_account_id` is a non-null FK) left-joined
through `Invoice` to `Vendor` (both nullable). Consequence: `ErpEntryRead` can no
longer be built by `model_validate(entry)` alone, so the list, voucher, and
detail endpoints all construct it from the joined row via one shared helper. The
detail endpoint uses the same join so a row looks identical in the table and in
the drawer.

### The `vendor_id` filter resolves through the source invoice

`WHERE source_invoice_id IN (SELECT id FROM invoices WHERE vendor_id = :v)`.

Entries with no source invoice can never match a supplier filter — which is
correct, not a bug: an unlinked posting has no known supplier. The empty state
says so rather than implying the supplier has no entries.

### Filter state lives in the URL

TanStack Router `validateSearch` on `/entries` owns `company_id`, `from`, `to`,
`entry_type`, `status`, `vendor_id`, and `page`. Consequences worth stating:

- The query key is derived from the validated search object, so React Query
  caches per filter combination for free.
- Changing any filter resets `page` to 1 — otherwise a narrowed filter strands
  the user on page 7 of a 2-page result, which reads as an empty state.
- Unset filters are omitted from the URL rather than serialized as empty
  strings, so the default view is a clean `/entries`.

### The page uses `Table` + `Pagination`, not `DataTable`

`ui/data-table.tsx` paginates client-side (`getPaginationRowModel`) over data it
already holds. Entries are paginated by the server, and rows are expandable
groups rather than flat records — neither fits. The page composes the styled
`Table` primitives with the existing `Pagination` component directly.

### Drawer is a new `ui/` primitive built on Base UI Dialog

The library has `Dialog` and `AlertDialog` but nothing side-anchored. Rather than
style a one-off panel inside the entries feature, `ui/drawer.tsx` wraps Base UI's
Dialog with side positioning (`side="right" | "left"`), inheriting its focus
trap, escape handling, and scroll lock. It is exported from the barrel and added
to the `/ui` route, so it is a library component with the same guarantees as the
rest — not entries-specific furniture.

### Filter option sources

- **Companies** — `GET /companies` (already used by settings).
- **Suppliers** — `GET /vendors`, which is already `q`-searchable and already
  scoped to the org's referenced vendors. Rendered as a `Combobox`, since a real
  org has more suppliers than a `Select` can hold.
- **Entry types** — derived from `GET /reports/entries-summary`, which already
  returns one row per `(entry_type, currency)`. This keeps the option list to
  types the org actually has, instead of hardcoding an enum the connectors are
  free to extend.
- **Statuses** — the fixed domain set (`pending`, `synced`, `failed`), since
  the absence of a status is itself meaningful and shouldn't vanish from the
  filter.

## Risks / Trade-offs

- **A pathologically large voucher** (thousands of postings) makes one group's
  entry list huge, since groups are never truncated. → Accepted for now:
  `page_size` for vouchers is capped (≤100, default 25) and real ERP vouchers are
  a handful of postings. If it bites, the fix is a per-group entry cap plus a
  "show all" that calls the flat endpoint with `voucher_id`.
- **Filter logic now exists in two endpoints** and can drift. → Both build their
  `WHERE` clause from one shared `_entry_conditions(...)` helper; a filter is
  added in one place or not at all.
- **Two round-trips per voucher page** instead of one. → Bounded and small; the
  second query is a single `IN` over at most `page_size` keys.
- **`ErpEntryRead` is no longer constructible from an `ErpEntry` alone**, so any
  future endpoint returning one must remember the join. → One `_entry_read(row)`
  helper is the only construction path, and the detail endpoint uses it too.
- **SQLite and Postgres order `NULL` differently** in `ORDER BY max(accounting_date)
  DESC` (Postgres puts NULLs first on DESC; SQLite last). Entries with no
  accounting date would land in different places in the two engines. → Order by
  `max(accounting_date) DESC NULLS LAST` explicitly, and assert the position of a
  null-dated group in a test so the difference cannot go unnoticed.
- **The nav change removes a signpost.** Users who expected an Invoices page lose
  the (disabled) hint that one is coming. → Acceptable: a disabled item promising
  a page nobody is building is worse than an enabled one that works. Invoices
  return as a nav entry if and when an invoice review UI is built.

## Migration Plan

No data migration — every column already exists and the additions are read-path
joins. Deployment is backend-then-frontend: the new endpoint and the additive
schema fields ship first and are backward compatible on their own (existing
clients ignore the new fields), then the frontend route lands. Rollback is
reverting the frontend; the extra endpoint is harmless if unused.

## Open Questions

- ~~Should a failed entry (`status = "failed"`) be visually escalated on the
  voucher row itself, or only visible once expanded?~~ **Settled: badge on the
  group row.** A failure that is only visible after expanding every voucher is
  not visible at all, which defeats the point of surfacing sync errors in the
  product. The badge repeats on the failing posting once expanded, so the row
  points at which one broke.
- `entry_type` values are connector-defined strings (`purchase_invoice`, …). They
  are shown raw for now; a display-label map belongs in a later change once the
  set of types across connectors is actually known.
