# Voucher detail panel — design

**Date:** 2026-08-08
**Status:** approved, ready for implementation planning

## Problem

Clicking a row on `/entries` opens `EntryDrawer` — a narrow, read-only drawer showing
one GL posting. That is not enough to review spend. The reviewer needs the scanned
invoice, the AI's categorization of its lines (which they must be able to correct),
the raw ERP postings behind the voucher, and the record of who changed what. Today
none of those are reachable from the entries table, the selection is held in
`React.useState` so it cannot be shared or survive a reload, and the drawer is
entry-scoped when the unit of review is the voucher.

## Scope

A voucher-scoped detail panel opened from the entries table, addressable by URL,
containing a PDF viewer, correctable AI fields, the voucher's ERP postings, and a
voucher-wide audit feed. Serving real PDF bytes end-to-end (mock ERP → connector →
web API → browser) is in scope. A general document-storage or upload capability is
not.

## The organizing principle: provenance decides affordance

CLAUDE.md states that the as-posted ERP columns "are never rewritten — they are the
evidence." Corrections apply only to what the AI produced: spend categorization and
invoice parsing. The panel makes that structural rather than remembered:

- **AI-produced values** render as real, focusable inputs.
- **ERP-posted values** render as flat text on a distinct tinted surface — never a
  disabled input, which still reads as tappable.

Enforcing this needs a provenance marker, so `Invoice` gains one column:

```python
source: str  # 'erp' | 'pdf_extraction', NOT NULL, default 'erp'
```

Sync-created invoices are `erp`; invoices produced by the PDF `InvoiceFlow` are
`pdf_extraction`. The column is the design's only schema change. Deriving provenance
from the presence of `raw_json` or `file_id` was rejected: both are incidental and
would silently mislabel a row the day either changes meaning.

## Backend

### Serving the document

Three pieces. No new Python dependencies — `weasyprint` and `jinja2` are already in
`pyproject.toml` — and no storage layer.

**mock_erp** — `GET /api/v1/documents/{voucher_id}` renders the purchase invoice
already generated in `mock_erp/data/invoices.py` through a Jinja2 template into a PDF
via WeasyPrint, memoized per voucher. `404` when the voucher has no invoice. Because
the PDF is rendered from the same data that was synced, the document genuinely agrees
with the stored rows, which is what makes correcting a parsed field testable.

**Connector** — a new abstract method on `ErpConnector`, beside the existing
`fetch_invoice_scan(voucher_id)` and keyed the same way:

```python
def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None
```

`DocumentPayload` carries `content: bytes`, `media_type: str`, `filename: str`.
`MockErpConnector` implements it against the route above. `None` means the voucher has
no attached document — distinct from a fetch that failed, which raises.

**web_api** — `GET /api/v1/invoices/{invoice_id}/document`, readable by any
authenticated member of the owning org.

- Tenant-scoped exactly like `get_invoice`: an invoice outside the caller's scope is
  indistinguishable from a missing one.
- `404` when `Invoice.file_id` is null — nothing is attached.
- Resolves the integration and the voucher key through the invoice's entries
  (`ErpEntry.source_invoice_id → erp_account_id → ErpAccount.erp_integration_id`), the
  path CLAUDE.md already documents. An invoice with no entries falls back to the
  company's connected integration when there is exactly one, and `404`s when there is
  none or more than one, rather than guessing.
- Decrypts that integration's credentials the same way the sync runner does.
- Streams the payload with `Content-Type: application/pdf` and
  `Content-Disposition: inline; filename="…"`.
- A connector failure returns `502` with a message the UI can show beside a retry
  action, never a broken or empty viewer.

`InvoiceRead` gains `file_id`, `file_name` and `has_document` (`file_id is not None`),
so any invoice payload states whether a document exists rather than making a client
probe the route to find out.

`VoucherDetailRead.document` below is derived from exactly those fields and is not an
independent source of truth: it is non-null precisely when the voucher's invoice has
`has_document`. It exists so the panel needs no second lookup, and the two must never
be computed differently.

**Accepted trade-off:** opening the panel hits the ERP synchronously. Acceptable at
this stage and explicitly the first thing that should gain a cache if it becomes a
problem.

### Reads

**`GET /api/v1/erp-entries/vouchers/{voucher_id}`** returns everything the panel needs
in one request:

```text
VoucherDetailRead
  voucher_id, company_id, accounting_date, currency, entry_count
  entries:  [ErpEntryRead]
  invoice:  InvoiceDetailRead | None   # includes its lines
  document: { file_id, filename } | None
```

Entries are built through the existing `_entry_select()` / `_entry_read()` pair so the
panel and the list cannot drift apart.

A sibling `GET /api/v1/erp-entries/vouchers/by-entry/{entry_id}` returns the same model
for voucher groups whose `voucher_id` is null — those form a group of one and have no
shareable key of their own. Both routes must be declared before
`/erp-entries/{entry_id}`, for the route-ordering reason already noted in
`erp_entries.py`.

`_EXCLUDED_ENTRY_TYPES` **does not apply to these routes.** CLAUDE.md exempts
`GET /erp-entries/{id}` from the payment exclusion because it is a lookup rather than a
listing; a voucher the user navigated to is the same case, so it shows all of its
postings, payments included. Hiding one would make the voucher's totals unexplainable.

**`GET /api/v1/erp-entries/vouchers/{voucher_id}/audit`** (and its `by-entry` sibling)
returns `AuditLog` rows for the voucher's invoice and every one of its lines, merged
and **newest-first**, each row carrying a resolved `entity_label` (the line's
description, or "Invoice") so the feed reads without a lookup per row — the same
reasoning that makes `ErpEntryRead` resolve its account and vendor server-side.
`AuditLog` is already generic over `entity_type` / `entity_id`, so this is a query, not
a migration.

The existing `GET /invoice-lines/{id}/audit` stays oldest-first and unchanged. The
difference is deliberate: a history reads forward, a feed reads backward.

### Writes

Line categorization uses the existing `POST /invoice-lines/{line_id}/verify` unchanged.
It already applies corrections, sets `verified`, appends an `AuditLog` row attributed
to the acting user, and recomputes the invoice rollup in one transaction.

**`PATCH /api/v1/invoices/{invoice_id}`** is added for parsed-header corrections:
management-gated, accepting only `invoice_number`, `invoice_date`, `currency`, `total`,
`tax` and `vendor_id`, appending an `AuditLog` row with `entity_type="invoice"`, and
returning **409** unless `source == 'pdf_extraction'`.

Noted honestly: no `pdf_extraction` invoices exist in the database today, so this
endpoint ships unused. It is included because it completes the stated correction rule,
and because the 409 branch is what proves the ERP-evidence guarantee holds under a
write attempt rather than only in the UI.

## Frontend

### URL state

Selection moves out of `React.useState` and into the route's search params, which is
what makes a shared link reopen the same panel over the same filtered list.
`validateEntrySearch` gains three keys:

- `voucher?: string` — the open voucher
- `entry?: string` — the null-`voucher_id` fallback key, and, when `voucher` is set,
  the posting to scroll to
- `tab?: 'details' | 'postings' | 'activity'` — defaulting to `details`, or `postings`
  when there is no invoice

Search params were chosen over a nested `/entries/$voucherId` route so that one
validated source of truth carries both the dialog and the filter context behind it; a
path route would carry the voucher and drop the filters unless it duplicated them into
search anyway.

`applyFilterChange` must clear `voucher` and `entry` alongside `page` — a voucher open
behind a filter change may no longer be in the result set.

### Components

Under `frontend/src/components/entries/`:

- `voucher-drawer.tsx` — shell, header, and the layout switch between the split and
  collapsed forms. Replaces `entry-drawer.tsx` as the entry point.
- `invoice-document.tsx` — the PDF pane: page navigation, zoom, download, loading
  skeleton, error-with-retry, and the no-document state.
- `voucher-details-tab.tsx` — the parsed invoice header plus the line categorization
  editors.
- `voucher-postings-tab.tsx` — the voucher's ERP postings. The existing `ConversionRows`
  logic moves here intact rather than being rewritten; it already explains a converted
  figure well.
- `voucher-activity-tab.tsx` — the audit feed.
- `line-category-editor.tsx` — one line's verify/correct form.

In `frontend/src/lib/entries.ts`: `voucherDetailQueryOptions`,
`voucherAuditQueryOptions`, and `invoiceDocumentQueryOptions` (fetching a blob through
the authenticated `ApiClient`, since the PDF route needs the Clerk token and so cannot
be an `<iframe src>`). Every mutation invalidates the voucher detail, the voucher
audit, and the voucher-groups list, because verifying a line changes the invoice
rollup the list displays.

`Drawer` gains a `size` variant — `max-w-md` (today's behaviour, the default) and a
wide form at `max-w-[1100px] w-[92vw]`. The width is currently hardcoded in
`DrawerContent`.

`react-pdf` is a new frontend dependency, installed with `bun add react-pdf` and
lazy-loaded via `React.lazy` so the pdf.js worker stays out of the main bundle.

### Layout and behaviour

**With an invoice:** wide drawer, PDF pinned in the left ~43% with the tabbed detail on
the right. The two panes scroll independently; the drawer itself does not scroll.
The document stays visible while the reviewer edits, which is the panel's entire
purpose — a parsed value and its evidence are never more than an eye-flick apart.

**Without an invoice** (a journal entry has no `source_invoice_id`, and this is the
common case): the PDF column and the Details tab are not rendered at all, and the panel
falls back to normal drawer width showing Postings and Activity. Not a wide panel of
empty frames, and no disabled tabs.

**Below ~1024px:** the split collapses to a stacked layout with the PDF as its own tab.

Interaction rules the implementation must honour:

- Dismissing with unsaved edits confirms first.
- Each AI categorization shows its confidence and its rationale — that is the thing the
  human is being asked to judge.
- The PDF's white page sits on a neutral surround rather than fighting dark mode.
- Focus moves into the panel on open; Base UI's dialog primitive already provides the
  focus trap, Esc dismissal and scroll lock, and must not be reimplemented.
- Read-only ERP values are distinguishable from disabled controls by surface and
  typography, not by opacity alone.

### Motion and rendering

Motion here is functional, not decorative: this is a review surface, and every
animation must express a cause and effect the reviewer already expects. Scroll-driven
storytelling, parallax depth and looping ambient motion are explicitly out of scope —
they would compete with the data.

- **Animate only `transform`, `opacity`, `filter` and `clip-path`.** Never width,
  height, top or left. The drawer's existing slide already follows this; the width
  variant must not regress it into an animated `max-width`.
- **`prefers-reduced-motion: reduce` collapses every transition to near-zero.** Non-
  negotiable, and it must be verified rather than assumed.
- **Exit is faster than enter** — roughly 130ms out against the existing 200ms in, so
  dismissal feels responsive rather than reluctant.
- **Tab switches crossfade in place**; content replacement inside one container should
  not slide, which would imply a spatial move that did not happen.
- **The audit feed staggers its rows by ~40ms on first paint**, and only on first
  paint. It is the one place where sequence carries meaning — the feed is chronological.
- **`will-change: transform` only while an element is actively animating**, removed
  afterwards, so an open panel is not permanently holding compositor layers.
- **The PDF renders visible pages only.** `react-pdf` will happily rasterize every page
  at once; pages are mounted through an `IntersectionObserver` (or `content-visibility:
  auto`) so a 40-page invoice does not stall the main thread on open.
- **Touch devices get reduced effects**, detected via
  `window.matchMedia('(pointer: coarse)')` — which is also where the layout has already
  collapsed to stacked.
- **Elevation is a consistent scale**, not per-component shadow values: scrim, drawer
  surface, and the raised PDF page are three defined steps.

## Testing

- **mock_erp:** the document route returns a PDF for a voucher that has an invoice and
  404s for one that does not.
- **Connector:** `fetch_invoice_document` returns a payload for a known voucher, `None`
  for a voucher with no scan.
- **web_api:** the document route is tenant-scoped (a foreign invoice 404s), 404s when
  `file_id` is null, and 502s when the connector raises. The voucher detail route
  returns postings, invoice and lines together; includes a `payment` posting when the
  voucher has one; and the `by-entry` variant resolves a null-`voucher_id` group. The
  audit route merges invoice and line rows newest-first. `PATCH /invoices` 409s on an
  `erp`-sourced invoice, succeeds on a `pdf_extraction` one, and writes an audit row.
- **Frontend:** the existing `entries-panel.test.tsx` pattern (render the presentational
  panel directly with fixture data) extends to the drawer — the split form renders with
  an invoice, the collapsed form renders without one, a URL carrying `voucher` opens the
  panel, and saving a corrected line calls verify and invalidates the list.

## Rejected alternatives

- **Rewriting entry/invoice fields in place**, with the audit log as the only record of
  the prior value. Destroys the as-posted evidence that reconciliation and FX recompute
  depend on.
- **A correction-overlay column set** beside every as-posted column. Every reader would
  then have to decide which value it means, for a capability nobody asked for.
- **A full-page `/entries/$voucherId` route.** More room, but the reviewer leaves the
  list, and sweeping twenty vouchers becomes twenty navigations.
- **Keeping the narrow drawer with the PDF in a tab.** A PDF at 560px is barely legible,
  and the document disappears exactly when the fields it explains come into view.
- **Building the viewer slot and deferring the bytes.** Would have shipped the headline
  feature as a placeholder.
