## Why

The Entries page groups postings by voucher and shows only the **expense** ones
when a group is expanded — VAT, payables and bank movements are dropped so the
visible rows add up to the group's figure. That hides most of the ledger. A user
reconciling against their ERP cannot see the postings the ERP actually holds,
and a voucher whose spend sits on one account offers no way in at all.

We want the expanded voucher to be the ledger: **one row per `ErpEntry`**, every
posting shown, each carrying its own `debit_amount − credit_amount`.

## What Changes

- An expanded voucher lists **every** posting — expense, VAT, liability, asset,
  income — not just spend. Account-type filtering is removed from the table
  entirely, along with the "show everything when the connector declares no
  types" fallback that only existed to cover for it.
- Each posting row's amount is that entry's own `debit_amount − credit_amount`,
  as one signed figure in the company's base currency. This is unchanged
  behaviour; it now simply applies to every posting rather than to the few that
  survived the filter.
- A voucher is expandable whenever it has **more than one posting**, rather than
  more than one *spend* posting. In practice almost every real voucher now
  expands, which is the point — the detail was always there and was unreachable.
- The group's amount column is renamed from **Total** to **Total Spend**. It
  still shows the server's net spend over the voucher's expense postings, but
  its children no longer sum to it — a balanced voucher's postings sum to zero —
  so the header must not read as a total of the rows beneath it.
- **BREAKING (behavioural, not API)**: the expanded view's rows no longer
  reconcile against the group figure. That invariant is deliberately given up in
  exchange for showing the whole ledger; the rename is what keeps it honest.
- **Money movements are dropped**: entries of type `payment` are excluded from
  `GET /api/v1/erp-entries` and `GET /api/v1/erp-entries/vouchers`. A payment
  settles an invoice that is already accounted for, so it is noise in a spend
  tool, and its postings sit on the payable and bank accounts a customer has no
  reason to enable for sync. A voucher made only of payment postings produces no
  group at all. The exclusion is deliberately narrow — `credit_note` (refunds)
  and `journal_entry` (accruals, corrections) both move real spend and stay.
- **BREAKING (API)**: this is a product rule, not a default. `entry_type=payment`
  returns an empty page rather than overriding it, and `total` counts only what
  is returned. `GET /erp-entries/{id}` is *not* gated — it is reached from a
  link, and 404-ing an in-tenant row that no listing offers would cost a working
  deep link for nothing.
- The Entries page's entry-type filter stops offering `payment`. Its options come
  from `entries-summary`, which reports over every entry, so it would otherwise
  offer a value that can only produce an empty table.
- The **Type column is dropped** from the table. With payments excluded, what is
  left is overwhelmingly `purchase_invoice`, so the column read the same on every
  row. Entry type stays in the drawer and as a filter. This also fixes a latent
  misalignment: the header had six columns while a posting row spanned five, so
  every posting's amount sat under Type instead of Total Spend.
- **Postings link to the invoice line they came from**, and the expanded rows
  gain a **Spend category** column showing that line's full category path
  (`Indirect › Legal › Professional Services`). New nullable FK
  `ErpEntry.source_invoice_line_id` (**migration 0017**), carried from the ERP
  through the connector DTO and derived — not matched — in the sync runner.
  **One line has many entries**, so several postings can share a category; VAT,
  the payable and journal entries have no line and stay empty, as does a line
  the categorizer has not reached yet. The entry itself is still never
  categorized: the category belongs to the line and is only resolved through it.
- The **mock ERP emits one expense posting per invoice line**, carrying that
  line's own description and net amount, instead of netting an invoice's lines
  per account into a single `"Vendor — Account name"` posting. `ErpEntry` already
  had a `description` and the sync already wrote it; the text simply had nothing
  in it worth reading. A generated invoice now produces 3–5 postings rather than
  always 3, and the accordion's expanded rows read like the invoice.
- **Both entry listings honour the account selection.** Entries on an account
  with `sync_enabled = false` are no longer returned. The toggle previously gated
  only the *fetch*, and since accounts are enabled when first discovered, every
  tenant accumulates rows on accounts the customer later deselected — which then
  kept showing on a page whose settings said otherwise. Filtered, not deleted, so
  re-enabling an account restores its history with no re-sync. Like the payment
  rule, this governs listings, not `GET /erp-entries/{id}`.
- **Consequence worth stating**: with the VAT and payable accounts deselected, an
  expanded voucher shows its expense postings only — no VAT, no payable, and its
  rows sum to Total Spend again rather than to zero. Enabling those accounts
  brings the full ledger view back. This is why the column is named *Total
  Spend*: it is correct in both configurations.
- **Bug fix — frozen base amounts.** `FxService.convert_row` treated the mere
  presence of a rate as proof that a row's stored conversion was current. Entries
  are upserted in place, so a row whose posted amounts changed kept the previous
  posting's base amounts — and since the table renders base amounts, it showed
  figures from unrelated rows, with the sign inverted where the old posting used
  the other ledger side. The short-circuit now requires the stored base amounts
  to still reproduce from the posted amounts at the stored rate. This also
  unbroke `POST /companies/{id}/recompute-fx`, which shares the same function and
  previously reported every corrupt row as unchanged.
- **Backend**: `GET /api/v1/erp-entries` gains a defined, stable ordering —
  `accounting_date` descending with undated entries last, then `voucher_id`,
  then `id`. This is retained as an **independent fix**: the endpoint had no
  specified order, undated entries sorted first, and an unstable order lets
  pagination repeat or drop a row. The Entries page does not call it.
- Filters, pagination, the detail drawer, and the loading/empty/error states are
  unchanged.

No endpoint or request parameter is added or removed, and
`GET /erp-entries/vouchers` already returned every posting in each group — that
filtering was the client's. `ErpEntryRead` does gain four response fields (the
source line and its three category levels), which is additive.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-erp-entries`: the requirement covering the voucher table changes —
  every posting is listed rather than only spend, expansion is offered on
  posting count rather than spend count, and the amount column is named
  Total Spend because the rows no longer sum to it. The filter requirement gains
  a rule that unlistable entry types are not offered.
- `web-api-entry-review`: both entry listings exclude `payment` entries, and
  `GET /api/v1/erp-entries` gains a specified ordering guarantee (dated first,
  undated last, a voucher's postings adjacent, stable).
- `mock-erp-api`: a purchase invoice produces one expense posting per invoice
  line, carrying that line's description, net amount and `lineNumber`, rather
  than one netted posting per account.
- `domain-model`: `ErpEntry` gains a nullable `source_invoice_line_id`, relating
  entries to lines as many-to-one; and the `sync_enabled` toggle now hides an
  account's entries from the listings as well as stopping future ingestion
  (retaining them, so it stays reversible).

## Impact

- **Frontend**
  - Modified: `frontend/src/components/entries/voucher-table.tsx` — `spendPostings()`
    removed, the expandability test and the column header changed.
  - `lib/entry-search.ts` gains `listableEntryTypes()`, used by the route to
    build the entry-type options.
  - `lib/types.ts` gains the four new `ErpEntryRead` fields.
  - `entries-panel.tsx`, `filter-bar.tsx`, `entry-drawer.tsx`,
    `converted-amount.tsx` and `lib/entries.ts` are untouched.
  - The signed-amount helpers move to `lib/entry-amount.ts` so the figure is
    computed in one place.
  - Tests: `entries-panel.test.tsx` — the "only spend postings" expectations are
    replaced by "every posting".
- **Backend**
  - `src/web_api/db/models/erp_entry.py` + **migration 0017** — the nullable FK,
    its index, and nothing backfilled (only a re-sync can supply the link).
  - `src/web_api/connectors/base.py` (`ErpEntryData.source_line_erp_id`),
    `connectors/mock.py`, and `ai_api/sync/runner.py` (`_source_line_id`).
  - `src/web_api/routers/erp_entries.py`: `_EXCLUDED_ENTRY_TYPES` applied in
    `_entry_conditions()` (both listings), `order_by` on the flat list, and an
    outer join to `InvoiceLine` in the one shared `_entry_select()`.
  - `src/web_api/schemas.py`: `ErpEntryRead` gains the line id and three
    category levels.
  - `src/web_api/reporting.py` is **not** touched. The report endpoints stay
    ledger-complete; only the entry listings drop payments. That is why the
    frontend, not the summary, filters the type options.
  - Tests: `tests/web_api/test_erp_entries.py` gains ordering and exclusion
    tests; its fixture's standalone payment voucher becomes a journal entry,
    since payments no longer surface.
- **Mock ERP**
  - `mock_erp/data/entries.py`: the per-account netting is replaced by one
    posting per invoice line. No schema or endpoint change — the same fields,
    with more rows and a description worth reading.
  - Tests: `tests/test_mock_erp.py` gains a test that a multi-line invoice's
    expense postings equal its lines, description and amount.
  - No change to `web_api/connectors/mock.py`, the sync runner, or `ErpEntry` —
    every one of them already carried `description` through.
- No database migration, no schema change, no change to the sync pipeline.
