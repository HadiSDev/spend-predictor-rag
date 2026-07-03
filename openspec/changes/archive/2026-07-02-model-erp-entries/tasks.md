## 1. Domain model & migration

- [x] 1.1 Add `file_id` (FK → `files`, nullable) to `Invoice` in `src/web_api/db/models/invoice.py`, plus a `file` relationship. Do NOT add a voucher column to `Invoice`
- [x] 1.2 Add `voucher_id` (text, nullable) to `ErpEntry` in `src/web_api/db/models/erp_entry.py`
- [x] 1.3 Wire `ErpEntry` ↔ `Invoice` relationship (back_populates) so an invoice exposes its `entries` and an entry its `source_invoice`; add a `files` back_populates/`invoices` relationship on `File` if needed
- [x] 1.4 Generate an additive Alembic migration for `invoices.file_id` (+FK) and `erp_entries.voucher_id`; run `uv run alembic upgrade head` against the dev DB
- [x] 1.5 Confirm `SQLModel.metadata.create_all` path (runner reset) also produces the new columns

## 2. Connector interface & DTOs

- [x] 2.1 Add `ErpEntryData` DTO to `src/web_api/connectors/base.py` (erp_entry_id, voucher_id, entry_type, erp_account_code, entry_date, description, debit_amount, credit_amount, currency, raw)
- [x] 2.2 Add `voucher_id` and an attached-file reference field to `ErpInvoiceData`
- [x] 2.3 Add abstract `fetch_entries(since: date | None) -> list[ErpEntryData]` and per-voucher `fetch_invoice_scan(voucher_id) -> ErpInvoiceData | None` to `ErpConnector`

## 3. Mock ERP: entries + voucher/file

- [x] 3.1 Extend the invoice generator (`mock_erp/data/invoices.py`) to assign each invoice a `voucherId` and an attached-file descriptor
- [x] 3.2 Add an entries generator that emits, per invoice voucher, reconciling entries (net + VAT + rounding) plus some non-invoice vouchers (payment/journal) with no scan
- [x] 3.3 Add `EntryResponse` (and voucher/file fields on `InvoiceResponse`) to `mock_erp/models.py`
- [x] 3.4 Add `GET /api/v1/entries` (pagination + optional `since`) to `mock_erp/main.py`; expose `voucherId` + file reference on purchase-invoice payloads
- [x] 3.5 Update `openspec/specs/mock-erp-api` endpoint listing / examples in the mock's docs if present

## 4. Mock connector implementation

- [x] 4.1 Implement `fetch_entries` in `src/web_api/connectors/mock.py` (paginate `/api/v1/entries`, map to `ErpEntryData`)
- [x] 4.2 Implement `fetch_invoice_scan(voucher_id)` (fetch/lookup the purchase invoice for a voucher; return `None` when absent); populate `voucher_id` + file reference on `ErpInvoiceData`

## 5. Sync runner: entry-first ingestion

- [x] 5.1 Reorder `run_sync` fetch stage to call `fetch_entries` and group entries by `voucher_id`; select invoice-bearing vouchers (`entry_type == purchase_invoice`)
- [x] 5.2 For each invoice-bearing voucher, fetch the scan; persist a `File` (deterministic id keyed by invoice_id+filename) when a document ref is present
- [x] 5.3 Update `_persist_invoices` to set `file_id` (NOT a voucher); build a transient `{voucher → invoice_id}` map scoped by integration as scans are persisted
- [x] 5.4 Add `_persist_entries` upserting `ErpEntry` rows (deterministic id keyed by integration_id+erp_entry_id) with their `voucher_id`, resolving `erp_account_id` from the persisted `ErpAccount`, and setting `source_invoice_id` from the voucher map (NULL when no scan)
- [x] 5.5 Ensure categorization stage is unchanged (runs only on `InvoiceLine`; entries untouched)
- [x] 5.6 Extend `_build_summary` / logging with entry counts (total, linked, unlinked)

## 6. Tests & verification

- [x] 6.1 Update/extend `tests/test_sync_runner.py`: entries persisted with `voucher_id`, multiple entries (sharing a voucher) link to one invoice, non-invoice entries have NULL `source_invoice_id`, invoice has `file_id` and no voucher column
- [x] 6.2 Add connector tests for `fetch_entries` (voucher-tagged, `since` filter) and `fetch_invoice_scan` (None for scan-less voucher)
- [x] 6.3 Add/extend mock ERP tests for `GET /api/v1/entries` pagination and entry↔invoice reconciliation
- [x] 6.4 Assert entries are NOT categorized after a sync run (ErpEntry categorization fields remain unset)
- [x] 6.5 Run `uv run pytest` (222 passed) and an in-process end-to-end run of the real runner + MockErpConnector + mock ERP (525/649 entries linked). NOTE: live uvicorn+Postgres `python -m ai_api.sync.runner` not run — infra not up in this env; migration validated offline only
