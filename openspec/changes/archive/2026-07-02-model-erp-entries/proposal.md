## Why

The sync pipeline fetches purchase invoices with embedded lines as if that were
the ERP's native shape. Real ERPs (e-conomic, Business Central, etc.) expose the
ledger as **entries** — individual GL postings — not as invoices. Each entry
carries a **voucher id**, and the scanned supplier invoice (its lines plus the
attached document file) is a *separate* resource keyed by that voucher. One
invoice scan is posted as **multiple entries** (net, VAT, rounding, split
accounts). Modelling invoices as the fetch unit loses the entry-level financial
truth, has no place for the ERP voucher id or the internal file reference, and
will not map onto any real connector we plug in next.

## What Changes

- **BREAKING**: Entries become the primary unit fetched from the ERP. The
  connector gains `fetch_entries(since)` returning normalized entry DTOs (each
  with a `voucher_id`); invoice scans are fetched *per voucher* rather than as a
  flat invoice list.
- The `ErpEntry` gains a `voucher_id` — the ERP voucher the posting belongs to.
  The **voucher lives on the entry, not on the invoice.**
- The `Invoice` gains a `file_id` reference into the internal **File** domain
  (the stored scan document). It does **not** store a voucher id.
- The `ErpEntry` ↔ `Invoice` link is formalized as **many-entries → one-invoice**,
  resolved through the shared voucher: entries carrying the same voucher attach to
  the one invoice scan for that voucher (`ErpEntry.source_invoice_id`). The
  voucher→invoice association is resolved at ingest time and is not persisted on
  the invoice.
- The sync runner’s persist stage is reordered: fetch entries → group by voucher
  → fetch/persist the invoice scan (with lines + file) for invoice-bearing
  vouchers → persist entries linked to that invoice → categorize.
- **AI/categorization is unchanged in scope**: it continues to run only on
  `Invoice` + `InvoiceLine`. Entries are stored as raw financial context and are
  **not** categorized by this change.
- The mock ERP API gains a `GET /api/v1/entries` endpoint (voucher-tagged
  postings) and exposes `voucherId` + an attached-file reference on purchase
  invoices, so the new fetch shape is exercised end-to-end deterministically.

## Capabilities

### New Capabilities
<!-- None. This change reshapes existing capabilities; no new spec is introduced. -->

### Modified Capabilities
- `domain-model`: `ErpEntry` gains `voucher_id`; `Invoice` gains `file_id`
  (FK → files) and does **not** store the voucher; `ErpEntry`→`Invoice` becomes an
  explicit voucher-resolved many-to-one; the entry-vs-invoice ownership rules and
  schema diagram are updated.
- `erp-connector-interface`: add `ErpEntryData` DTO and `fetch_entries(since)`;
  invoice scans are retrieved per voucher; the sync-runner integration ordering
  changes to entry-first.
- `mock-erp-api`: add `GET /api/v1/entries` (voucher-tagged) and expose
  `voucherId` + attached-file reference on purchase-invoice payloads.

## Impact

- **Domain / ORM** (`web_api/db/models/`): `invoice.py` (+`file_id`, relationship
  to `File`); `erp_entry.py` (+`voucher_id`, relationship wiring); a new Alembic
  migration.
- **Connector** (`web_api/connectors/`): `base.py` (new DTO + abstract
  `fetch_entries`, voucher-keyed scan fetch); `mock.py` implementation.
- **Sync runner** (`ai_api/sync/runner.py`): fetch/persist reordering, new
  `_persist_entries`, voucher→invoice grouping, summary counts for entries.
- **Mock ERP** (`mock_erp/`): new entries data generator + endpoint; voucher id
  and file reference on invoices; `models.py` response schemas.
- **Tests**: `tests/test_sync_runner.py`, connector tests, mock-erp tests.
- Categorizer, aggregation, redundancy, and recommender are **unaffected**
  (still consume `InvoiceLine`).
