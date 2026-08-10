# Invoice field corrections

## Why

A reviewer can currently correct exactly one thing about an invoice: a line's
spend category. Everything else the pipeline parsed — the supplier, the invoice
number, the date, the total, the VAT, and every descriptive field on a line — is
presented as flat, uneditable evidence. When the extraction is wrong, or when
the ERP itself posted the wrong figure, the reviewer's only recourse is to
requeue the document and hope the model does better.

Two facts make this worse than the design intends:

1. **The correctable path is unreachable.** `PATCH /invoices/{id}` 409s unless
   `Invoice.source == 'pdf_extraction'`, but **nothing in production ever sets
   that value** — the sync writes the `'erp'` default and the document stage
   never changes it. Every real invoice therefore renders as read-only text, and
   the header editor that already exists in the voucher panel has never been
   shown to a customer.
2. **A human correction has nowhere to survive.** `_persist_invoices` rewrites
   `invoice_number`, `invoice_date`, `currency`, `total` and `tax` on every
   re-sync, and refreshes ERP lines the same way. Editing in place today means
   editing until the next sync.

There is a second reason beyond review ergonomics: a human's corrected value is
the **label** for the field the AI got wrong. Today that signal is thrown away.
A verification action that records what a human settled turns routine review
into a labelled dataset for evaluating and improving extraction.

## What Changes

- **Correcting an invoice is no longer gated on provenance.** `PATCH
  /invoices/{id}` accepts an ERP-sourced invoice. Values are edited **in place**
  — there is no parallel `corrected_*` column set — and every field-level change
  is written to `AuditLog`, which is where the ERP's original value remains
  recoverable. **BREAKING**: the `409 Conflict` on a non-`pdf_extraction`
  invoice is removed.
- **New `POST /invoices/{id}/verify`**, mirroring `POST
  /invoice-lines/{id}/verify`: apply corrections, mark the header human-verified,
  audit the diff, in one transaction. Verification is a distinct auditable
  action, not a flag folded into an ordinary edit.
- **A verified field is never overwritten by a sync.** The invoice and the line
  each record which fields a human settled; `_persist_invoices` refreshes
  everything else exactly as it does now and skips those. A `--hard-reset` flag
  on the sync runner is the single, explicit escape hatch that restores the ERP's
  values over a human's.
- **The supplier becomes correctable in two ways that never touch shared data.**
  The invoice may be re-pointed at a different `Vendor` (or a newly created one),
  and its supplier **name, country and VAT number** may be corrected as
  invoice-scoped overrides stored on the invoice. `Vendor` is a global catalog
  row shared across tenants, so one organization's correction must not rewrite
  another's supplier.
- **Line fields become correctable**: `description`, `quantity`, `unit`,
  `unit_price` and `amount`, alongside the spend category the line editor already
  handles. `native_account_code` stays read-only — it is the ledger's own
  statement of where the money was posted, and a human contradicting it produces
  a line that reconciles against nothing.
- **Lines can be added and deleted.** Splitting one stand-in line into several
  is the main way a reviewer improves an `entry_fallback` invoice. A delete is
  audited and unlinks (never deletes) the postings that referenced the line.
- **A correction that breaks reconciliation warns, and never blocks.** When the
  lines no longer sum to the invoice total (within the document stage's existing
  tolerance), the invoice and its voucher panel carry a visible mismatch with the
  delta. A reviewer part-way through a multi-line fix must not be blocked by
  their own half-finished work.
- **The voucher panel's Details and Lines tabs become editors** for every field
  above, with the same dirty-state, cancel and save discipline the header editor
  already has, and management-gated writes.

## Capabilities

### New Capabilities

- `invoice-field-corrections`: what a human may correct on a parsed invoice and
  its lines, how a correction is recorded and verified, how corrections and the
  ERP sync coexist, and how a broken reconciliation is surfaced.

### Modified Capabilities

- `web-api-invoice-review`: `PATCH /invoices/{id}` loses its provenance gate and
  gains supplier-override and vendor-repoint fields; new `POST
  /invoices/{id}/verify`; new `PATCH`/`POST`/`DELETE` for invoice lines; invoice
  and line payloads carry verified-field state and the reconciliation delta.
- `sync-pipeline-orchestration`: `_persist_invoices` must not overwrite fields a
  human verified, on either the invoice or its lines; a `--hard-reset` flag
  overrides that deliberately.
- `frontend-erp-entries`: the voucher panel's Details tab edits the full header
  for any invoice regardless of provenance; the Lines tab edits line fields and
  supports add/delete; the mismatch warning is surfaced.
- `audit-log`: the auditable field sets grow (supplier overrides, line
  descriptive/amount fields) and gain the `verify`, `line_added` and
  `line_deleted` actions on the invoice entity.
- `domain-model`: `Invoice` gains supplier-override columns and a verified-field
  record; `InvoiceLine` gains a verified-field record and a `human` origin.
- `invoice-document-processing`: automatic replacement is skipped for an invoice
  with human-verified lines; the reconcile tolerance becomes one shared rule
  serving both the extraction decision and the payload's reconciliation report.

## Impact

**Schema** (one Alembic migration): `invoices` gains `supplier_name`,
`supplier_country_code`, `supplier_vat_number`, `verified_fields`,
`verified_at`, `verified_by`; `invoice_lines` gains `verified_fields`.

**API** (`src/web_api/`): `routers/invoices.py` (PATCH gate removed, verify
added), `routers/invoice_lines.py` (line PATCH / POST / DELETE), `schemas.py`
(`InvoiceUpdate`, `InvoiceVerify`, `InvoiceLineUpdate`, `InvoiceLineCreate`,
plus read-model additions), `audit.py` (field sets and actions), `rollup.py`
(unchanged rollup, re-run after line add/delete), `reconcile` helper shared with
the document stage.

**Sync** (`src/ai_api/sync/runner.py`): `_persist_invoices` becomes
verified-aware; the CLI gains `--hard-reset`.

**Frontend** (`frontend/src/`): `components/entries/voucher-details-tab.tsx`,
`voucher-lines-tab.tsx`, `line-category-editor.tsx`, `lib/invoices.ts`,
`lib/types.ts`, plus a vendor picker reusing the existing `/vendors` endpoint.

**Not affected**: reporting (reads the same columns), FX (the existing
"correcting currency/total/tax nulls the base amounts" rule is retained and
extended to lines), spend trees, connectors.
