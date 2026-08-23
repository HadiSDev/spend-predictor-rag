## 1. Schema and migration

- [x] 1.1 Add `item_name: Optional[str] = Field(sa_type=String, nullable=True)` to `InvoiceLine` in `src/web_api/db/models/invoice_line.py`, beside `description`, with a comment stating why the two are separate
- [x] 1.2 Write migration `0006_line_item_name.py` chaining from `0005_invoice_corrections` (revision id under 32 characters — `alembic_version.version_num` is `varchar(32)`): add the column, `UPDATE invoice_lines SET item_name = description`, then `SET description = NULL`
- [x] 1.3 In the same migration, rewrite each row's `verified_fields` JSON array, replacing `"description"` with `"item_name"`, so a human's settled field follows the value it settled
- [x] 1.4 Write the downgrade: copy `item_name` back into `description`, reverse the `verified_fields` rewrite, drop the column
- [x] 1.5 Run `uv run pytest tests/web_api/test_migrations.py` — the chain must run from base against a throwaway PostgreSQL

## 2. Backend: item name through the API

- [x] 2.1 Add `item_name: str | None = None` to `InvoiceLineRead` in `src/web_api/schemas.py`
- [x] 2.2 Add `item_name: str | None = None` to `InvoiceLineUpdate` (inherited by `InvoiceLineCreate`)
- [x] 2.3 Add `"item_name"` to `LINE_VALUE_AUDIT_FIELDS` in `src/web_api/audit.py`; verify it propagates to `replace.py::_REMOVED_FIELDS` and `runner.py::_WITHDRAWN_FIELDS`, which splat that tuple
- [x] 2.4 Test: `PATCH /invoice-lines/{id}` with `item_name` stores it, marks it in `verified_fields`, and writes an audit row carrying the old value
- [x] 2.5 Test: a categorization field sent alongside `item_name` is still a 422

## 3. Backend: the printed invoice number becomes correctable

- [x] 3.1 Add `document_invoice_number: str | None = None` to `InvoiceUpdate` in `src/web_api/schemas.py`
- [x] 3.2 Add `"document_invoice_number"` to `INVOICE_AUDIT_FIELDS` in `src/web_api/audit.py` — required, since the correction is applied in place and the audit row is the only record of what the extractor read
- [x] 3.3 Confirm `document_invoice_number` is **not** in the FX-trigger set, so correcting it does not clear the invoice's base figures
- [x] 3.4 Test: correcting it stores the value, audits the old one, leaves `invoice_number` untouched, and leaves `base_total`/`fx_rate` untouched
- [x] 3.5 Test: `POST /invoices/{id}/verify` marks `document_invoice_number` verified when sent

## 4. AI: extraction returns a name and a description

- [x] 4.1 Add `item_name: str | None` to `LineItem` in `src/ai_api/models.py`, with a field description telling the model to give the product/service name without quantities, prices or terms
- [x] 4.2 Update the text and vision extraction prompts to ask for the split, stating that a line with only one text puts it in `item_name` and leaves `description` null
- [x] 4.3 In `src/ai_api/documents/replace.py`, persist `item_name=item.item_name` on the new `InvoiceLine`, and apply the one-text fallback (if `item_name` is null and `description` is set, move it)
- [x] 4.4 Test: an extraction stating both stores both; an extraction stating one stores it as `item_name` with a null `description`
- [x] 4.5 Test: a removed line's `superseded_by_extraction` audit row carries its `item_name`
- [x] 4.6 Re-run the document corpus and compare the read count against the current baseline — the split must not cost documents that read today
  - Ran against VectorLab ApS (the real Billy corpus): 23 invoices that had read cleanly.
  - **First pass 20/23.** Cause found: `_is_summary_row` was reading `item.description`,
    which this change empties — so the filter silently stopped filtering and receipts
    counted their item *and* their total. Two documents came back at exactly 2x their
    own total. Fixed in `vision.py` (`item.item_name or item.description`) and pinned by
    tests in `test_summary_rows.py` that fail against the bug.
  - **Second pass 21/23.** The remaining 2 were control-tested with the prompt change
    reverted and failed *identically* (2049.74 and 523.0), so they are pre-existing
    failures of the current extractor, not a cost of this change. The stale `processed`
    baseline had been accumulated across earlier code versions.
  - Net: the split costs nothing. One real regression was introduced, found, and fixed.

## 5. Sync: both line paths write the item name

- [x] 5.1 Add `item_name: str | None = None` to `ErpInvoiceLineData` in `src/web_api/connectors/base.py`
- [x] 5.2 Map the bill line's text to `item_name` in `src/web_api/connectors/billy.py` (~L552) and `src/web_api/connectors/mock.py` (~L115), leaving `description` null
- [x] 5.3 In `src/ai_api/sync/runner.py` (~L500), `assign_line("item_name", line.item_name)` alongside the existing description assignment
- [x] 5.4 In `_persist_standin_lines` (~L836), write the posting's description to `item_name` and leave `description` null
- [x] 5.5 Route `_persist_standin_lines` writes through `_assigner()` so `verified_fields` is respected on that path — it currently assigns directly, so a corrected stand-in line is overwritten by the next sync
- [x] 5.6 Test: a corrected stand-in line survives a re-sync; `--hard-reset` still overwrites it and audits the overwrite as actor `system`
- [x] 5.7 Test: an untouched stand-in line still refreshes when the posting's memo changes
- [x] 5.8 Verify against the Billy fixtures in `tests/fixtures/billy/` — no network

## 6. Frontend: types and the CurrencyInput

- [x] 6.1 Add `item_name: string | null` to `InvoiceLineRead` and `item_name?: string | null` to `InvoiceLineUpdate` in `frontend/src/lib/types.ts`; add `document_invoice_number?: string | null` to `InvoiceUpdate`
- [x] 6.2 Build `frontend/src/components/ui/currency-input.tsx` wrapping `NumberInput`: takes a currency code, resolves symbol and scale via `Intl.NumberFormat` (as `lib/format.ts::formatMoney` does), emits `floatValue ?? null` — never a string, never `NaN`
- [x] 6.3 Right-align and use tabular figures, so a column of amounts is scannable
- [x] 6.4 Export `CurrencyInput` from `frontend/src/components/ui/index.ts`
- [x] 6.5 Tests: formats for its currency, emits a number not a string, emits `null` when cleared, renders as a plain 2-decimal field with no currency code
- [x] 6.6 Add it to the kitchen-sink route `frontend/src/routes/ui.tsx`

## 7. Frontend: typed controls replace the text boxes

- [x] 7.1 Lift `toIsoDate` / `fromIsoDate` out of `frontend/src/components/entries/filter-bar.tsx` (L96-107, currently private) into `frontend/src/lib/format.ts`, with tests
- [ ] 7.2 In `line-editor.tsx`, move `unit_price` and `amount` to `CurrencyInput` and `quantity` to `NumberInput` (up to 4 decimals, trailing zeros trimmed)
- [ ] 7.3 In `voucher-details-tab.tsx`, move `total` and `tax` to `CurrencyInput` and `invoice_date` to `DatePicker` (submitting `YYYY-MM-DD`)
- [ ] 7.4 Replace the `Number(current[field])` conversion in **both** editors with the controls' parsed numeric values, so unparseable input can never be submitted as `null`
- [ ] 7.5 Make the dirty check compare **parsed values**, not input strings — a formatter normalizing `1234.50000` to `1,234.50` on mount must not report the card as dirty (see design D4 risk)
- [ ] 7.6 Test: a line stored as `1234.50000` displays `1,234.50`; typing `1,5` never submits `null`; opening and saving an unedited `0.2500` quantity does not change the stored value

## 8. Frontend: the paged Lines tab

- [ ] 8.1 Rewrite `voucher-lines-tab.tsx` around a single rendered line card with Previous / Next and an `N of M` indicator; keep `ReconciliationNotice` and the Add-line control outside the card
- [ ] 8.2 Order by `sequence` with `id` as tiebreak; mount exactly one card (no hidden siblings — their inputs stay focusable and their state alive)
- [ ] 8.3 Disable Previous on the first line and Next on the last; no wrapping
- [ ] 8.4 Seed the shown line from the line the table activated: extend the table's selection to carry the line id, and use it as the initial index only — component state, not a search param (see design D3)
- [ ] 8.5 Keyboard: named buttons reachable by Tab; Left/Right arrows page **only** when focus is outside a text-entry control
- [ ] 8.6 Dirty guard: paging away from an edited card confirms first; declining keeps the edits; a clean card pages with no prompt
- [ ] 8.7 Directional transition — Next enters from the trailing edge, Previous from the leading edge; `transform`/`opacity` only; under 250ms; fully suppressed under `prefers-reduced-motion`; nothing loops at rest
- [ ] 8.8 Empty invoice: keep the existing empty state, render no navigation and no indicator
- [ ] 8.9 Tests for every scenario in `specs/frontend-line-paging/spec.md`

## 9. Frontend: item name and the invoice numbers

- [ ] 9.1 Label lines by `item_name ?? description ?? placeholder` in `voucher-table.tsx`'s `LineRow` and on the paged card
- [ ] 9.2 Add an `Item name` field to the line card, above `Description`, and keep `Description` as its own field
- [ ] 9.3 Bind the Details tab's editable "Invoice number" to `document_invoice_number`
- [ ] 9.4 Show the ERP's `invoice_number` in the panel's leading metadata block as read-only text, labelled so it is not mistaken for the supplier's number
- [ ] 9.5 Leave the field empty when `document_invoice_number` is null — never backfill it from the posted value
- [ ] 9.6 Tests: the name is the label with description as fallback; the editable field corrects the document number; the posted number renders as metadata

## 10. Verification

- [ ] 10.1 `uv run pytest`
- [ ] 10.2 `cd frontend && ./node_modules/.bin/tsc --noEmit`
- [ ] 10.3 `cd frontend && ./node_modules/.bin/vitest run`
- [ ] 10.4 `cd frontend && ./node_modules/.bin/eslint src` — no new errors (line 39 of `voucher-table.tsx` has a pre-existing one)
- [ ] 10.5 Hand over the dev-server commands and confirm the panel by eye: page a multi-line invoice, correct an amount, correct the invoice number, check the audit feed shows both old values
