# Tasks — invoice field corrections

## 1. Schema and domain model

- [x] 1.1 Add `supplier_name`, `supplier_country_code` (String(2)), `supplier_vat_number`, `verified_fields` (JSON, default `[]`), `verified_at` (tz-aware datetime), `verified_by` (str) to `Invoice` in `apps/web-api/src/web_api/db/models/invoice.py`, each documented with why it exists (override ≠ vendor write; per-field, not per-row).
- [x] 1.2 Add `verified_fields` (JSON, default `[]`) to `InvoiceLine` in `apps/web-api/src/web_api/db/models/invoice_line.py`.
- [x] 1.3 Add `HUMAN = "human"` to `LineOrigin` in `apps/web-api/src/web_api/db/models/enums.py`, documenting its precedence above `document_ai`.
- [x] 1.4 Write one Alembic revision on the current head adding the six invoice columns and the one line column; all nullable or server-defaulted so existing rows need no backfill. Verify `uv run alembic upgrade head` then `downgrade -1` both run clean.
- [x] 1.5 Confirm `apps/web-api/tests/test_migrations.py` still runs the chain from base against PostgreSQL (skips without one).

## 2. Shared rules moved into the domain

- [x] 2.1 Move the reconcile tolerance rule out of `apps/ai-api/src/ai_api/documents/reconcile.py` into `apps/web-api/src/web_api/reconcile.py`: a function taking the lines' sum, `total` and `tax` and returning `(reconciled, delta)` against `total` / `total − tax` within `max(pct, abs)`. Keep the `DOC_RECONCILE_TOLERANCE_*` env names.
- [x] 2.2 Re-point `ai_api/documents/` at the moved rule so the accept/reject decision and the read-side report cannot diverge. Existing document-stage tests must pass unchanged.
- [x] 2.3 Add `verified.py` (or extend `audit.py`) in `web_api` with the helpers both the API and the sync need: `mark_verified(row, fields)`, `is_verified(row, field)`, `clear_verified(row, fields)` — normalizing to a sorted, deduped list.
- [x] 2.4 Extend `INVOICE_AUDIT_FIELDS` with the three supplier overrides; add `LINE_VALUE_AUDIT_FIELDS` (`description`, `quantity`, `unit`, `unit_price`, `amount`) and `LINE_BASE_FX_FIELDS` (`base_currency`, `base_amount`, `fx_rate`, `fx_rate_date`) in `apps/web-api/src/web_api/audit.py`.

## 3. Invoice header API

- [x] 3.1 Extend `InvoiceUpdate` in `apps/web-api/src/web_api/schemas.py` with `supplier_name`, `supplier_country_code`, `supplier_vat_number`; keep `vendor_id`.
- [x] 3.2 Remove the `source != "pdf_extraction"` 409 from `update_invoice` in `apps/web-api/src/web_api/routers/invoices.py`; keep the management gate, the base/FX clearing and the `edit`/`noop` audit distinction.
- [x] 3.3 Validate `vendor_id` against an existing `Vendor`, returning `422` with nothing written.
- [x] 3.4 Add `POST /invoices/{id}/verify` taking an optional `InvoiceVerify` body (same fields as `InvoiceUpdate`): apply, `mark_verified` with the fields **sent**, set `verified_at`/`verified_by`, audit as `edit` or `verify`, one transaction, management-gated, `404` out of scope.
- [x] 3.5 Extend `InvoiceRead`/`InvoiceDetailRead` with `verified_fields`, `verified_at`, `verified_by`, the resolved supplier trio (`override ?? vendor.value`) and `supplier_overrides` naming which are overridden; batch the vendor lookup in the list path so no row lazy-loads.
- [x] 3.6 Add `lines_reconciled` and `reconciliation_delta` (signed, null when reconciled or when `total` is null) to `InvoiceDetailRead`, computed through `web_api/reconcile.py`.
- [x] 3.7 Tests: ERP-sourced PATCH succeeds; supplier override does not mutate the `Vendor` row; unknown `vendor_id` → 422; `member` → 403; verify with and without a body (`verify` vs `edit`); resubmitting an unchanged value records `noop` yet still marks the field verified; other tenant → 404.

## 4. Invoice line API

- [x] 4.1 Add `InvoiceLineUpdate` (`description`, `quantity`, `unit`, `unit_price`, `amount`; `extra="forbid"`) and `InvoiceLineCreate` (same plus optional `sequence`) to `schemas.py`.
- [x] 4.2 Add `PATCH /invoice-lines/{id}` in `apps/web-api/src/web_api/routers/invoice_lines.py`: apply in place, clear the line's base/FX fields when `amount` moves, audit the whole diff, recompute the invoice rollup, management-gated, `404` out of scope.
- [x] 4.3 Reject a categorization field or `native_account_code` on that PATCH with a `422` naming the right endpoint, rather than ignoring it.
- [x] 4.4 Add `POST /invoices/{id}/lines`: create with `origin=human`, `status=uncategorized`, `sequence` defaulting after the last line; audit `line_added` on the invoice entity; recompute the rollup.
- [x] 4.5 Add `DELETE /invoice-lines/{id}`: NULL `source_invoice_line_id` on every referencing `ErpEntry`, audit `line_deleted` on both the line and the invoice carrying the line's values and categorization, delete, recompute the rollup — one transaction.
- [x] 4.6 Record verified fields on `POST /invoice-lines/{id}/verify` too, so both surfaces produce labels identically.
- [x] 4.7 Extend `InvoiceLineRead` with `verified_fields`; confirm `origin` serializes `human`.
- [x] 4.8 Tests: description PATCH audits the diff; amount PATCH clears the line's base amount in the same audit entry; a category field is 422; add-then-delete splits a stand-in and leaves postings with a null line reference; deleting the last categorized line recomputes the rollup; `viewer` is 403 on all three.

## 5. Sync runner

- [x] 5.1 Replace the bare field assignments in `_persist_invoices` (`apps/ai-api/src/ai_api/sync/runner.py`) with an `assign_unverified` helper that skips fields listed in the row's `verified_fields`; apply to both the invoice and its ERP lines.
- [x] 5.2 Add `hard_reset: bool = False` to `run_sync()` and a `--hard-reset` CLI flag; when set, assign regardless, audit each overwrite with actor `system`, and drop the overwritten names from `verified_fields`.
- [x] 5.3 Make `_queue_document` skip an invoice whose lines include a `verified` or `human` one, leaving `doc_status` as it is.
- [x] 5.4 Tests: a verified `total` survives a re-sync while `invoice_date` refreshes; `--hard-reset` overwrites, audits with actor `system` and clears that field's verified mark; a `human` line survives both a plain sync and a hard reset; a new document does not queue an invoice with verified lines, while an unverified one still queues.

## 6. Document stage

- [x] 6.1 Confirm `POST /invoices/{id}/reprocess` still queues and replaces on an invoice with verified lines — the explicit human path is unaffected.
- [x] 6.2 Ensure a replaced line that carried human verification is audited with `superseded_by_extraction` carrying its verified values.
- [x] 6.3 Test both, plus that an accepted extraction is reported as `lines_reconciled` true by the invoice payload (one rule, one verdict).

## 7. Frontend — client and types

- [x] 7.1 Extend `apps/web/src/lib/types.ts`: `InvoiceUpdate` supplier fields, `InvoiceVerify`, `InvoiceLineUpdate`, `InvoiceLineCreate`, the new read-model fields, and `'human'` in the line origin union.
- [x] 7.2 Add the calls to `apps/web/src/lib/invoices.ts`: `verifyInvoice`, `updateInvoiceLine`, `createInvoiceLine`, `deleteInvoiceLine`, each invalidating the voucher/invoice queries the panel reads.

## 8. Frontend — header editor

- [x] 8.1 In `voucher-details-tab.tsx`, gate `EditableInvoiceHeader` on the management role instead of `source === 'pdf_extraction'`; keep `ReadOnlyField` for read-only roles and keep the provenance badge for both.
- [x] 8.2 Add currency, and the three supplier fields — country from `lib/countries.ts` as a selector, not a text input.
- [x] 8.3 Add a searchable vendor picker over `GET /vendors`, following the spend-tree selector's "chosen, never typed" rule.
- [x] 8.4 Mark an overridden supplier field visibly and keep the catalog value reachable; state that the correction applies to this invoice only.
- [x] 8.5 Add the verify action, showing verifier and time once verified; hide it for read-only roles.
- [x] 8.6 Preserve the existing dirty-state discipline: `key={invoice.id}` remount, baseline updated on save, only changed fields sent, dirty reported up for the drawer's dismissal guard.

## 9. Frontend — lines editor

- [x] 9.1 Extend `line-category-editor.tsx` with description, quantity, unit, unit price and amount inputs beside the category selector, routing category to verify and the rest to the line PATCH.
- [x] 9.2 Add "Add line" and per-line delete to `voucher-lines-tab.tsx`, with an explicit confirmation naming the line being deleted; render neither for read-only roles.
- [x] 9.3 Mark a `human` line the way `ProvenanceMark` marks a provisional one — text plus a mark, never colour alone.
- [x] 9.4 Show the reconciliation warning on the Lines tab with both figures and the signed delta, and surface it in the drawer header so it is visible from any tab; clear it when the lines come back within tolerance.

## 10. Verification

- [x] 10.1 `uv run pytest` green.
- [x] 10.2 Frontend tests green (`./node_modules/.bin/vitest run` from `apps/web/`), including updated `voucher-details-tab.test.tsx`, `voucher-lines-tab.test.tsx` and `voucher-drawer.test.tsx`.
- [ ] 10.3 Run the sync against the Debug ERP twice with a verification in between and confirm the corrected value survives, then once with `--hard-reset` and confirm it is restored and audited. **Not done — needs the dev database.** `run_sync()` reads its work list from connected `ErpIntegration` rows, so this would mean writing a company + integration into the developer's own PostgreSQL, which is theirs to do. The same sequence runs automatically against a throwaway engine in `apps/ai-api/tests/test_sync_verified_fields.py` (survives a re-sync / restored and audited by `--hard-reset` / human lines outlive both).
- [x] 10.4 Update `CLAUDE.md`: the provenance-decides-affordance paragraph (postings only now), the new endpoints, `verified_fields`, the supplier overrides, the `human` origin, and `--hard-reset`.
