## 1. Schema and domain model

- [x] 1.1 Add `origin` to `InvoiceLine` (`src/web_api/db/models/invoice_line.py`), non-null, with an enum of `erp | document_ai | entry_fallback` in `db/models/enums.py`
- [x] 1.2 Add `doc_status`, `doc_attempts`, `doc_error`, `doc_processed_at` to `Invoice` (`db/models/invoice.py`), with a `DocStatus` enum of `not_applicable | pending | processing | processed | failed`
- [x] 1.3 Write one Alembic revision on `0001_baseline_schema` adding all five columns with their defaults
- [x] 1.4 Backfill in the same revision: every existing line to `origin='erp'`; invoices with a `file_id` to `doc_status='pending'`, the rest to `'not_applicable'`
- [x] 1.5 Add indexes `invoices(doc_status, invoice_date)` and `invoice_lines(invoice_id, origin)`
- [x] 1.6 Verify the chain runs from base on PostgreSQL via `tests/web_api/test_migrations.py`

## 2. Sync runner: stand-in lines and queueing

- [x] 2.1 Add an expense-posting predicate to `ai_api/sync/runner.py`, reusing the same account-type logic `_voucher_amount()` uses so the stand-in lines and the voucher total agree on what counts as spend
- [x] 2.2 Write stand-in lines: one `InvoiceLine(origin='entry_fallback')` per expense posting, deterministically keyed off the posting so a re-sync upserts rather than duplicates
- [x] 2.3 Take description, amount, account code and currency from the posting; convert at the invoice's `invoice_date` through the existing `FxService` path
- [x] 2.4 Set `ErpEntry.source_invoice_line_id` on the posting each stand-in line was written for
- [x] 2.5 Skip stand-in materialization entirely when the invoice already has `document_ai` lines, or when the ERP supplied `erp` lines
- [x] 2.6 Set `doc_status` when persisting an invoice: `pending` with a document, `not_applicable` without; leave `processing` untouched; return a `processed` invoice to `pending` when the sync attaches a different document
- [x] 2.7 Add the queued-invoice count to the per-integration run report
- [x] 2.8 Tests: a scanless voucher yields one line per expense posting and none for VAT/payable; a split-account voucher yields two; re-sync does not duplicate; `document_ai` lines survive a re-sync; a voucher of only non-expense postings yields no line

## 3. Document-processing stage

- [x] 3.1 Create `src/ai_api/documents/` with a `runner.py` that discovers `doc_status='pending'` invoices across every connected integration, oldest `invoice_date` first, mirroring `connected_integrations()` in the sync runner
- [x] 3.2 Claim each invoice by committing `doc_status='processing'` before any work, so two overlapping runs cannot take the same invoice
- [x] 3.3 Fetch the document through the invoice's integration connector (the path `GET /invoices/{id}/document` uses); persist no bytes
- [x] 3.4 Dispatch on the payload's media type: PDFs through `ai_api/pdf_loader.py`; record a clean unsupported-media failure for types with no extractor
- [x] 3.5 Extract lines using the `flow.py` extraction agents, reusing `ai_api/parsing.py` for JSON repair (prompt for JSON, do not use guided decoding)
- [x] 3.6 Reconcile: accept if the lines sum to `total` or to `total − tax` within `max(1% × |total|, one currency unit)`; skip the check when `total` is null; otherwise reject
- [x] 3.7 On rejection, record `doc_status='failed'` with both sums in `doc_error`, increment `doc_attempts`, and leave the invoice's lines untouched
- [x] 3.8 Cap attempts at a configured ceiling; skip invoices that have reached it until retriggered
- [x] 3.9 Isolate failure per invoice — an exception records `failed` on that invoice and the run continues; exit non-zero if any invoice failed
- [x] 3.10 Add `--company-id`, `--invoice-id` and `--limit`, which filter the discovered set and never create work
- [x] 3.11 Add stage settings to `ai_api/config.py`: attempt ceiling, reconciliation tolerance, stale-claim age
- [x] 3.12 Tests against fixture documents with no network and no live LLM: discovery, claiming, per-invoice isolation, the attempt ceiling, and each reconciliation branch

## 4. Line replacement

- [x] 4.1 Write the replacement in one transaction: delete the invoice's `erp`/`entry_fallback` lines, null `source_invoice_line_id` on any posting that referenced them, insert the `document_ai` lines
- [x] 4.2 Convert the new lines at the invoice's `invoice_date` through the existing FX path; leave them `uncategorized` — the stage never categorizes
- [x] 4.3 Append an `AuditLog` row per removed line via `web_api/audit.py`, `actor='system'`, carrying the removed line's categorization result and status
- [x] 4.4 Recompute `Invoice.status` through `web_api/rollup.py` in the same transaction
- [x] 4.5 Set `doc_status='processed'`, `doc_processed_at`, and clear `doc_error`
- [x] 4.6 Tests: stand-ins are fully replaced; a verified line's values survive in the audit log; a re-extraction leaves exactly one set of lines; a `verified` invoice rolls back to `uncategorized`; postings are unlinked and their category reads null

## 5. Web API

- [x] 5.1 Add `origin` to `InvoiceLineRead`, and `doc_status`/`doc_error`/`doc_processed_at` to `InvoiceRead` (`web_api/schemas.py`)
- [x] 5.2 Carry `lines` plus the invoice's `doc_status`/`doc_error` on `VoucherGroupRead` and `VoucherDetailRead`, resolved server-side and deterministically ordered
- [x] 5.3 Build the line resolution through the existing `_entry_select()`/`_entry_read()`/`_entry_conditions()` structure in `routers/erp_entries.py` so the flat list, the groups and the detail endpoint cannot drift; leave `_voucher_amount()` and the grouping untouched
- [x] 5.4 Add `voucher_id`, `vendor_id`, `origin` and `from`/`to` filters to `GET /invoice-lines`, with `from`/`to` bounding the invoice date and `vendor_id` resolving through the invoice
- [x] 5.5 Add `POST /invoices/{id}/reprocess` (management role): returns the invoice to `pending`, clears `doc_error`, resets `doc_attempts`; `409` when there is no document or the invoice is `processing`; `404` out of scope; audited with the acting user
- [x] 5.6 Tests: voucher payloads carry lines and processing state; a voucher with no invoice returns an empty line list; grouping/pagination/amounts are byte-identical to before; each new `/invoice-lines` filter and their composition; every reprocess status code and the role gate

## 6. Frontend

- [x] 6.1 Extend the voucher types in `frontend/src/lib/entries.ts` with the lines array, `doc_status` and `doc_error`
- [x] 6.2 Rewrite the expanded-group renderer in `components/entries/voucher-table.tsx` to list invoice lines with Description, Quantity, Spend category and Amount headers, keeping the `colSpan` alignment invariant
- [x] 6.3 Make a group expandable when its voucher has at least one line; a voucher with no lines stays an ordinary row that still opens the panel
- [x] 6.4 Keep the group figure as the server's Total Spend — never a sum of the lines
- [x] 6.5 Add a Postings tab to the voucher panel listing every `ErpEntry` with account, type, date, description, debit, credit, status and error, as flat evidence text with no disabled inputs; carry the tab in the URL
- [x] 6.6 Make the Lines tab the tab that opens when a line is activated from the table, and the place a line's category is corrected
- [x] 6.7 Add the provenance mark for `entry_fallback` lines, explained on hover and to assistive technology, presented as information rather than an error; leave `document_ai` lines unmarked
- [x] 6.8 Show `doc_status` on the panel, with `doc_error` beside a retrigger action; offer the action only for a management role on an invoice that has a document and is not `processing`; show "no document attached" plainly with no control
- [x] 6.9 Wire the reprocess mutation in `lib/invoices.ts` and invalidate the voucher and line queries so the panel updates without a reload
- [x] 6.10 Add the `origin` filter to `lib/entry-search.ts` and the filter bar, carried in the URL, composing and clearing with the rest
- [x] 6.11 Update the affected tests in `components/entries/` — `voucher-table`, `entries-panel`, `voucher-postings-tab`, `voucher-details-tab` — to the line-based contract, and add tests for the provenance mark and the retrigger affordance

## 7. Verification and documentation

- [x] 7.1 Run the full suite: `uv run pytest` and the frontend tests
- [x] 7.2 Run `uv run alembic upgrade head` from an empty PostgreSQL database and confirm the backfill against seeded rows
- [x] 7.3 Run the sync runner then the document stage against the Debug ERP end to end, and confirm the page shows stand-in lines that are then replaced by extracted ones
- [ ] 7.4 Benchmark extraction against `ai_api/synthdata` ground truth before pointing the stage at Billy — **blocked**: no model server is reachable (nothing on :8000 or :8001), so the LLM leg has never been run. Everything around it is verified end to end against real Billy data (discovery → claim → live fetch → media dispatch → PDF text).
- [x] 7.5 Update `CLAUDE.md`: the document-processing stage and its command, `origin` and `doc_status`, the reprocess endpoint, the line-based Entries page, and the Postings tab
