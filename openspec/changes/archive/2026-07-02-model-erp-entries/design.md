## Context

The sync pipeline (`ai_api/sync/runner.py`) currently drives:
`connect → fetch_invoices → persist Invoice+InvoiceLine → categorize`. The
connector's `fetch_invoices` returns invoice headers with embedded lines, and the
mock ERP serves them at `GET /api/v1/purchase-invoices`.

Real ERPs (e-conomic, Business Central, Visma) do not model the ledger that way.
The atomic record is an **entry** (GL posting) that carries a **voucher** id. One
posted supplier invoice becomes several entries (net, VAT, rounding, split
accounts). The scanned invoice document — its line items plus the stored PDF — is
a *separate* resource attached to the voucher. So the real fetch shape is:
entries first, invoice scans looked up per voucher.

The ORM already anticipates this: `ErpEntry` exists with `source_invoice_id`,
`erp_entry_id`, and a `raw_json`; `File` exists. What is missing is a
`voucher_id` on `ErpEntry` (the entry's own attribute, and the join key), an
`Invoice.file_id` column, a connector method to fetch entries, and a runner that
ingests entry-first. This change closes that gap while keeping AI/categorization
exactly where it is today (on `Invoice` + `InvoiceLine`).

## Goals / Non-Goals

**Goals:**
- Make **entries** the primary unit fetched from the ERP, each tagged with a
  `voucher_id`.
- Retrieve invoice scans **per voucher**, and link every entry of a voucher to the
  one `Invoice` scan for that voucher (`ErpEntry.source_invoice_id`).
- Add `voucher_id` to `ErpEntry` and `file_id` (FK → `files`) to `Invoice`, and
  create a `File` row for each scan's attached document. The invoice stores no
  voucher.
- Reorder the runner to entry-first and persist entries as raw financial context.
- Extend the mock ERP with `GET /api/v1/entries` and voucher/file fields on
  invoices so the flow runs deterministically end-to-end.

**Non-Goals:**
- **No categorization of entries.** AI operations stay on `Invoice`/`InvoiceLine`;
  `ErpEntry` categorization columns are left untouched (dormant) by this change.
- No change to aggregation, redundancy, or recommender inputs (still
  `InvoiceLine`).
- No real ERP connector implementation — only the interface + mock.
- No re-basing spend metrics onto entries; invoice-scan totals remain the source
  for invoice figures.

## Decisions

### D1 — Voucher lives on the entry; `source_invoice_id` is the resolved FK
`ErpEntry` carries `voucher_id`; **`Invoice` does not.** During persist the runner
fetches the scan per voucher, so it already holds the `(voucher → invoice_id)`
pairing in the loop; it uses that transient map to set `ErpEntry.source_invoice_id`
for entries whose voucher matched a scan. Entries for vouchers with no scan keep
`source_invoice_id = NULL`. The voucher→invoice association is never persisted on
the invoice row.
- *Why:* the voucher is the entry's own attribute (a posting can be a payment or
  journal with no invoice at all). Tagging the invoice with a voucher would
  duplicate a fact that belongs to the entry and misrepresent scan-less vouchers.
- *Alternative rejected:* store `voucher_id` on `Invoice` too. Redundant — the
  invoice is reachable from any of its entries via `source_invoice_id`, and the
  ingest loop already knows the voucher; persisting it on the invoice adds a
  column with no unique consumer.
- *Alternative rejected:* a separate `Voucher` table. Overkill now — the voucher
  is just an identifier on the entry; a table adds a join with no consumer. Can be
  introduced later if vouchers grow attributes.

### D2 — Add `voucher_id` to `ErpEntry`; add only `file_id` to `Invoice`
`ErpEntry.voucher_id` (text, nullable). `Invoice.file_id` (FK → `files`,
nullable). `erp_id`/`invoice_number` keep their meaning (native invoice number).
- *Why:* the scanned document is a first-class fact the invoice must hold
  (`file_id`); the voucher is a first-class fact the *entry* must hold
  (`voucher_id`). Neither is conflated into `erp_id`.

### D3 — Connector gains `fetch_entries` + per-voucher scan lookup
Add DTO `ErpEntryData` and abstract `fetch_entries(since) -> list[ErpEntryData]`.
Invoice scans are obtained per voucher via `fetch_invoice_scan(voucher_id) ->
ErpInvoiceData | None`; `ErpInvoiceData` gains an attached-file reference. The
runner already knows the voucher (it called `fetch_invoice_scan(voucher_id)`), so
the voucher is not persisted on the invoice — it is stored on the entries and used
transiently to link them.
- *Why:* matches the real fetch shape and lets the runner drive off the entry set.
- *Alternative considered:* keep only `fetch_invoices` and derive entries from it.
  Rejected — it inverts reality (invoices are derived from entries, not the
  reverse) and can't represent non-invoice vouchers.
- *Efficiency note:* per-voucher fetch risks N calls. The mock can serve scans
  from an in-memory map, and a real connector can batch; the interface allows a
  bulk `fetch_invoice_scans(voucher_ids)` later without breaking callers.

### D4 — Runner ordering: entries → group by voucher → scans → link → categorize
New stage order in `run_sync`:
1. `fetch_accounts`, `fetch_vendors`, `fetch_entries`.
2. Group entries by `voucher_id`; select invoice-bearing vouchers
   (`entry_type == purchase_invoice`).
3. For each such voucher, `fetch_invoice_scan`; persist `File` (if a document
   ref is present), then `Invoice` (+`file_id`) and its lines. Record the
   `(voucher → invoice_id)` pairing in a transient map.
4. `_persist_entries`: upsert all entries (each with its `voucher_id`), setting
   `source_invoice_id` from the transient voucher→invoice map.
5. Categorize `InvoiceLine` (unchanged).
- Deterministic IDs continue via `_det_id(...)`: `file` keyed by
  `(invoice_id, filename)`, `entry` keyed by `(integration_id, erp_entry_id)`.

### D5 — Mock ERP: generate entries from the same seed as invoices
Each generated invoice is tied to a voucher and an attached-file descriptor; the
ERP payload exposes `voucherId` so the connector can resolve a scan per voucher
(our domain stores the voucher on the entries, not on the invoice). An entries
generator emits, per invoice voucher, a net entry + a VAT entry (and rounding when
needed) that reconcile to the invoice, plus some non-invoice vouchers
(payments/journal entries) to prove `source_invoice_id` NULL. New endpoint `GET /api/v1/entries` with the standard pagination + `since`.
- *Why:* keeps synthetic entries and invoices mutually reconcilable, satisfying
  the mock-erp-api spec and giving the runner realistic linkage to test.

## Risks / Trade-offs

- **Per-voucher scan fetch is N round-trips** → mitigate by serving from an
  in-memory map in the mock and leaving room for a batch method in the interface;
  real connectors can page scans.
- **Schema migration** (one FK column `file_id` on `invoices`, one `voucher_id`
  column on `erp_entries`) → additive and nullable, so backfill-free; existing
  rows get NULL.
- **Voucher collisions across integrations** → always scope the
  voucher→invoice map and deterministic ids by `erp_integration_id`/`company_id`,
  never by bare voucher string.
- **Dormant `ErpEntry` categorization columns** could imply entries get
  categorized → the domain spec explicitly states entries are not categorized;
  runner never touches those columns.
- **Reconciliation drift** between generated entries and invoice totals →
  generator derives entries *from* the invoice amounts, not independently.

## Migration Plan

1. Add `Invoice.file_id` + relationship and `ErpEntry.voucher_id`; wire `ErpEntry`
   relationships. Generate one additive Alembic migration (nullable columns + FK).
2. `uv run alembic upgrade head` (dev DB is disposable; the sync runner also
   `create_all`s on reset).
3. Land connector DTO/method changes and mock ERP endpoint together (mock is the
   only implementation, so no broken connectors).
4. Update runner + tests; run `python -m ai_api.sync.runner` against the mock to
   verify entries persist and link.
- **Rollback:** revert the migration (drop the two columns) and the code; no data
  loss since columns are additive and nullable and entries are additive rows.

## Open Questions

- Exact real-ERP field names for voucher id and attachment (per ERP) — deferred
  until the first real connector; the DTO normalizes them.
- Whether non-invoice entries (payments, journals) should later feed
  aggregation/redundancy — out of scope; they persist now but are unused.
- Should a bulk `fetch_invoice_scans(voucher_ids)` be added now or when a real
  connector needs it — leaning "later" to keep this change focused.
