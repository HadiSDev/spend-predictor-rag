## 1. Backend — flat list ordering

- [x] 1.1 In `src/web_api/routers/erp_entries.py`, change `list_erp_entries`'s
  `order_by` to `nulls_last(ErpEntry.accounting_date.desc())`,
  `nulls_last(ErpEntry.voucher_id)`, `ErpEntry.id`, with a comment saying why
  (voucher adjacency; `id` makes the order total so pagination cannot repeat or
  skip; `nulls_last` because SQLite and PostgreSQL disagree on NULL placement).
- [x] 1.2 In `tests/web_api/test_erp_entries.py`, add a test that two vouchers
  posted on the same `accounting_date` come back with each voucher's postings
  consecutive rather than interleaved.
- [x] 1.3 Add a test that entries with no `accounting_date` are returned after
  all dated ones.
- [x] 1.4 Run `uv run pytest tests/web_api/test_erp_entries.py` and confirm the
  existing tests still pass.

## 2. Frontend — shared amount helpers

- [x] 2.1 Create `frontend/src/lib/entry-amount.ts` and move `postingAmount` and
  `basePostingAmount` there unchanged from
  `frontend/src/components/entries/voucher-table.tsx`, keeping the comments that
  explain the `?? 0` (connectors send `0.00`, not null).
- [x] 2.2 Update `voucher-table.tsx` to import them, and confirm no other module
  defined its own copy.

## 3. Frontend — every posting in the accordion

- [x] 3.1 Delete `spendPostings()` from `voucher-table.tsx` and render
  `group.entries` directly, so no posting the API returned is withheld. The
  account-type fallback goes with it — a filter that is not there cannot empty
  the table.
- [x] 3.2 Change the expandability test from "more than one spend posting" to
  `group.entries.length > 1`, and rewrite the comment that justified the old
  test (it argued most vouchers do *not* expand; the opposite is now true and
  intended).
- [x] 3.3 Keep the single-entry case as it is: no chevron, and the row itself
  opens that posting's drawer, so a lone voucherless posting stays reachable.
- [x] 3.4 Rename the amount column header from `Total` to `Total Spend`, and
  update `GroupAmount`'s doc comment to say the figure is net spend and is
  deliberately not the sum of the rows beneath it.
- [x] 3.5 Confirm `EntryRow` needs no change — it already renders one signed
  `postingAmount` per entry through `ConvertedAmount`.

## 4. Frontend — revert the view toggle

- [x] 4.1 Delete `frontend/src/components/entries/entry-table.tsx`; the
  accordion's child rows are the one-row-per-entry view.
- [x] 4.2 Remove the `Tabs` view control and the `view`/`onViewChange` props from
  `filter-bar.tsx`.
- [x] 4.3 Revert `entries-panel.tsx` to a single `result: Page<VoucherGroupRead>`
  prop — no discriminated union, no `onViewChange`, count label back to
  vouchers. Keep the reworded "no ERP data synced yet" copy.
- [x] 4.4 Remove `applyViewChange`, `entryFilters`, and the `view` parsing from
  `lib/entry-search.ts`, and retype `applyFilterChange` back to `EntryFilters`.
- [x] 4.5 Remove `EntryView` and `EntrySearch` from `lib/types.ts`.
- [x] 4.6 Remove `entriesQueryOptions` and the `QueryToggle` `enabled` option from
  `lib/entries.ts`; nothing calls the flat endpoint from the client.
- [x] 4.7 Revert `routes/_authed/entries.tsx` to one query and one panel render.

## 5. Frontend tests

- [x] 5.1 In `entries-panel.test.tsx`, drop the `EntriesPanel — entry rows` and
  `EntriesPanel — view toggle` suites and the `setupEntries` helper, and restore
  the single `setup`/`setupProps` props factories.
- [x] 5.2 Replace `reveals only the spend postings when spend is split` with a
  test that expanding shows **every** posting, VAT and payable included.
- [x] 5.3 Replace `does not offer to expand a voucher with a single spend line`
  with a test that a three-posting voucher *is* expandable, and keep a test that
  a single-entry group is not.
- [x] 5.4 Add a test that an expanded voucher's posting amounts sum to zero, and
  that the group's figure is not that sum.
- [x] 5.5 Update the column-header assertions to `Total Spend`, keeping the
  checks that no Debit or Credit column exists.
- [x] 5.6 Keep the "never prints a zero for an unused side" test — it now covers
  the payable row, which is exactly the row that carries `0.00`.
- [x] 5.7 Remove the view cases from `lib/entry-search.test.ts`, and the
  `entriesQueryOptions` cases from `lib/entries.test.ts`.
- [x] 5.8 Run `./node_modules/.bin/vitest run` and `./node_modules/.bin/tsc --noEmit`
  from `frontend/` and confirm both are clean.

## 6. Backend — exclude money movements

- [x] 6.1 Add `_EXCLUDED_ENTRY_TYPES = ("payment",)` to
  `src/web_api/routers/erp_entries.py`, with a comment saying why payments are
  noise in a spend tool and why the set stays narrow (credit notes and journal
  entries move real spend).
- [x] 6.2 Apply it unconditionally in `_entry_conditions()`, so both listings get
  it and `entry_type=payment` composes to an empty page rather than overriding.
- [x] 6.3 Leave `GET /erp-entries/{id}` ungated, with a comment recording that
  the rule governs listing, not lookup by id.
- [x] 6.4 Retype the `seed_entries` fixture's standalone payment voucher as a
  `journal_entry` (`PAY1` → `JE1`), since its role in those tests is to be a
  second voucher, and update the tests that named it.
- [x] 6.5 Add a `JE9` journal-entry voucher touching no expense account to
  `seed_typed_accounts`, so "spent nothing → no amount" is still covered now
  that payments never reach the response.
- [x] 6.6 Add tests: payments absent from the voucher groups; absent from the
  flat list with `total` agreeing with `items`; `entry_type=payment` returning
  an empty page; a credit note still returned.
- [x] 6.7 Run `uv run pytest` and confirm the whole backend suite passes.

## 7. Frontend — do not offer an unlistable filter

- [x] 7.1 Add `listableEntryTypes()` and its `EXCLUDED_ENTRY_TYPES` constant to
  `lib/entry-search.ts`, commented to name the server-side rule it mirrors and
  why the duplication exists (the options come from `entries-summary`, which
  reports over every entry).
- [x] 7.2 Use it in `routes/_authed/entries.tsx` in place of the inline
  dedupe-and-sort.
- [x] 7.3 Add tests covering: `payment` dropped; credit notes and journal
  entries kept; dedupe and sort preserved.
- [x] 7.4 Run `vitest run` and `tsc --noEmit` and confirm both are clean.

## 8. Frontend — drop the Type column

- [x] 8.1 Remove the `Type` header and its group cell from `voucher-table.tsx`,
  along with the now-unused `entry_types` destructuring, with a comment on why
  (payments are excluded, so the column reads the same on every row).
- [x] 8.2 Note that this also squares the header with the five cells a posting
  row spans — the header was six, so posting amounts sat under Type rather than
  Total Spend.
- [x] 8.3 Add a test that no Type column header exists, and a test that a
  posting row's cells (counting `colSpan`) span exactly the header's column
  count.
- [x] 8.4 Run `vitest run` and `tsc --noEmit`.

## 9. Mock ERP — one posting per invoice line

- [x] 9.1 In `mock_erp/data/entries.py`, replace the `net_by_account` netting
  with one `_emit` per invoice line, using the line's `netAmount` as the debit
  and its `description` as the entry description, falling back to
  `"{vendor} — {account name}"` for a line with no text.
- [x] 9.2 Update the module docstring, which described a net debit per expense
  account.
- [x] 9.3 Confirm reconciliation still holds — the line net amounts already sum
  to the invoice net, so debit = credit = gross.
- [x] 9.4 Add a test in `tests/test_mock_erp.py` that a **multi-line** invoice's
  expense postings equal its lines pairwise on description and amount.
- [x] 9.5 Run `uv run pytest` and confirm the whole backend suite passes.

## 10. Frontend — label the expanded postings

- [x] 10.1 Add a `PostingHeaderRow` to `voucher-table.tsx` rendering **Account**,
  **Description** and **Amount** as real `<th>` cells, rendered once per open
  group, with a comment on why the table's own header cannot serve (it names a
  voucher's columns) and why the figure is "Amount" not "Total Spend".
- [x] 10.2 Rework the alignment test to compare the voucher header row, the
  posting header row and a posting row by summed `colSpan`, scoping the header
  lookup to `thead` now that there is more than one header row on the page.
- [x] 10.3 Add a test that the three sub-headers are present once a group is
  expanded.
- [x] 10.4 Run `vitest run` and `tsc --noEmit`.

## 11. Spend category on the postings

- [x] 11.1 Add nullable `ErpEntry.source_invoice_line_id` FK to `invoice_lines`,
  with a comment recording that one line has many entries and that null is the
  ordinary case.
- [x] 11.2 Write migration `0017_entry_source_line` (column + named FK + index),
  backfilling nothing, and verify upgrade → downgrade → upgrade on PostgreSQL.
- [x] 11.3 Add `ErpEntryData.source_line_erp_id`; emit `lineNumber` from the mock
  generator (null on VAT/payable) and map it in `connectors/mock.py`, keeping the
  None rather than stringifying it.
- [x] 11.4 Add `_source_line_id()` to the runner: derive the line id from
  `(invoice, line_erp_id)` — the same pair `_persist_invoices` uses — and fall
  back to null when the row does not exist, so a dangling reference cannot abort
  a sync.
- [x] 11.5 Add `source_invoice_line_id` + `spend_category_level_1/2/3` to
  `ErpEntryRead`, resolved by one outer join to `InvoiceLine` in `_entry_select()`
  so all three endpoints agree. Append after index 5, which `_net_spend` reads
  positionally.
- [x] 11.6 Backend tests: a posting reports its line's category; two postings
  share one line's category; no line → null; uncategorized line → null levels;
  the voucher groups carry it too; the runner links and handles a dangling id;
  the mock emits `lineNumber` and the connector maps it.
- [x] 11.7 Frontend: add the fields to `ErpEntryRead`, a `SpendCategory`
  component rendering the full path with the leaf emphasised, and a
  **Spend category** sub-column. Drop the account cell's `colSpan={2}` so the
  posting rows stay five wide.
- [x] 11.8 Frontend tests: full path shown; empty before categorization; a
  missing level leaves no dangling separator.
- [x] 11.9 Run `uv run pytest`, `vitest run` and `tsc --noEmit`.

## 12. Fix frozen FX on re-posted rows

- [x] 12.1 In `web_api/fx/service.py`, make `convert_row`'s short-circuit require
  that the stored base amounts still reproduce from the posted amounts at the
  stored rate, not merely that a rate is present. Materialize `amount_fields`,
  which is now iterated twice on that path.
- [x] 12.2 Add tests: a changed posted amount is reconverted; a posting that
  swaps ledger sides clears the side it no longer uses; an untouched row still
  costs no rate lookup.
- [x] 12.3 Correct the two requirements that authored the wrong rule — they live
  in the unarchived `company-base-currency` change, not in `openspec/specs/`.

## 13. Listings honour the account selection

- [x] 13.1 Add the `sync_enabled` condition to `_entry_conditions()` as a
  subquery (the count query has no account join), with a comment on why the
  fetch-time gate alone leaves rows visible.
- [x] 13.2 Leave `GET /erp-entries/{id}` and `reporting.py` alone, consistent
  with the payment rule.
- [x] 13.3 Tests: a deselected account's entries are absent from both listings
  and from `total`; absent from their voucher group's `entries`/`entry_count`;
  a voucher of only deselected postings yields no group; re-enabling restores
  them with no re-sync; detail by id still resolves.
- [x] 13.4 Amend the `domain-model` requirement that said entries "SHALL NOT be
  deleted or hidden by the toggle" — the retention half stands, the visibility
  half flips.

## 14. Documentation

- [x] 14.1 Note the flat list's ordering guarantee in `CLAUDE.md` alongside the
  `/erp-entries` filters.
- [x] 14.2 Note the `payment` exclusion in `CLAUDE.md`, on both entry listings.
