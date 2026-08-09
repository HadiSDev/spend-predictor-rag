## Why

The Entries page presents GL postings as the unit of spend, but a posting is an
accounting artifact, not a purchase. "Kontorartikler 3.200,00" on account 1310 is
what the bookkeeper wrote; the two monitors and the dock the company actually
bought are on the attached document, and only the document knows them. A spend
tool that categorizes postings can never say more than the ledger already said,
so redundancy detection and product-level savings — the whole point of the
product — have nothing to work with.

The invoice **line** is the right unit: it is what carries a description, a
quantity, a category and a human verification. This change makes the line the
thing the Entries page shows and the thing the AI produces, by processing each
voucher's attached document after the ledger lands. When a voucher has no
document, or processing fails, each expense posting stands in as a line so the
page is never empty and categorization still runs — a floor, replaced the moment
a real extraction succeeds.

## What Changes

- **The Entries page shows invoice lines.** Vouchers stay as the grouping and
  the drawer keeps its identity, but an expanded voucher row lists its
  **invoice lines** — description, quantity, amount, spend category — instead of
  its postings. The postings survive as evidence on their own drawer tab.
  **BREAKING** for the page's expanded-row contract and its tests.
- **A new AI document-processing stage.** After the sync lands a voucher's
  entries and its scan, a separate background stage (`ai_api`) fetches the
  document, extracts its lines, and writes them as `InvoiceLine` rows. It runs
  out of band: a slow or failing LLM never blocks or delays the ledger sync.
- **Stand-in lines when there is no document.** The sync materializes one
  `InvoiceLine` per **expense** posting on a voucher that has no extracted
  lines. VAT, the payable and other non-expense postings never become lines.
  These are real rows — the categorizer, `/invoice-lines/{id}/verify`, the audit
  log and the reports all work on them unchanged.
- **Lines record their provenance and invoices record their processing state.**
  `InvoiceLine.origin` distinguishes `erp` / `document_ai` / `entry_fallback`;
  `Invoice.doc_status` tracks `not_applicable | pending | processing | processed
  | failed` with an attempt count and an error. The page reads both, so a
  stand-in line is visibly provisional rather than silently passed off as
  extracted detail.
- **Processing can be retriggered.** `POST /invoices/{id}/reprocess`
  (management) puts a failed or stale invoice back to `pending`; the next stage
  run picks it up. A successful extraction **replaces** that invoice's stand-in
  lines.
- **The API serves lines where it served postings.** The voucher group and
  voucher detail payloads carry the voucher's lines alongside its entries, and
  `GET /invoice-lines` gains the filters the page needs (voucher, date range,
  vendor, origin, status).

## Capabilities

### New Capabilities

- `invoice-document-processing`: the out-of-band AI stage that turns an
  invoice's attached document into `InvoiceLine` rows — how work is discovered,
  the per-invoice status machine, replacement of stand-in lines, retriggering,
  and how failure degrades rather than blocks.

### Modified Capabilities

- `domain-model`: `InvoiceLine` gains `origin`; `Invoice` gains the
  document-processing status fields. The rule that a line is the only
  categorizable unit is unchanged and reinforced.
- `sync-pipeline-orchestration`: the runner materializes stand-in lines from
  expense postings and marks invoices `pending` for document processing; it
  never calls the document AI itself.
- `web-api-entry-review`: voucher groups and voucher detail carry their invoice
  lines; entry payloads keep their existing link to the line they came from.
- `web-api-invoice-review`: `GET /invoice-lines` gains voucher/date/vendor/
  origin filters; `POST /invoices/{id}/reprocess` is added; line payloads carry
  `origin`.
- `categorization-lifecycle`: the categorizer runs on stand-in and extracted
  lines alike; replacing a stand-in line is an audited event.
- `frontend-erp-entries`: expanded vouchers list lines, not postings; postings
  move to their own drawer tab; processing state and line provenance are shown,
  with a retrigger action.

## Impact

- **Schema / migration**: `invoice_lines.origin`; `invoices.doc_status`,
  `doc_attempts`, `doc_error`, `doc_processed_at`. One Alembic revision on top
  of `0001_baseline_schema`; existing rows backfill to `origin='erp'` and
  `doc_status='not_applicable'`.
- **`src/ai_api/`**: new `documents/` stage (discovery, extraction, line
  replacement) reusing `flow.py`'s extraction agents and `pdf_loader.py`;
  `sync/runner.py` gains stand-in line materialization.
- **`src/web_api/`**: `schemas.py` (line `origin`, invoice doc status, voucher
  payloads), `routers/erp_entries.py`, `routers/invoices.py`,
  `routers/invoice_lines.py`, `rollup.py`, `audit.py`.
- **`frontend/`**: `components/entries/` — the expanded-row renderer, a new
  lines tab, the postings tab, provenance and processing affordances;
  `lib/entries.ts`, `lib/invoices.ts`, `lib/entry-search.ts`.
- **Reporting is unaffected in shape** but changes in content: `spend-by-category`
  already reads categorized lines, and those lines become product-level once
  extraction runs.
- **Operational**: a second scheduled process alongside the sync runner, and the
  document AI now reaches the ERP per invoice to download scans.
