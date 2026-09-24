# Design — invoice field corrections

## Context

Today the only human correction the product supports is a line's spend category
(`POST /invoice-lines/{id}/verify`, resolved against the company's spend tree).
Everything else is read-only, for a reason the codebase states explicitly:
provenance decides affordance — ERP-posted values are evidence, and a disabled
input claims a permission that will never be granted.

Two facts undermine that position in practice.

**The correctable path does not exist.** `PATCH /invoices/{id}` requires
`Invoice.source == 'pdf_extraction'`, but the string appears in production code
only in that comparison. `_persist_invoices` constructs invoices with the `'erp'`
default and the document stage never changes it. `EditableInvoiceHeader` in
`voucher-details-tab.tsx` has therefore never rendered against real data.

**In-place edits do not survive.** `_persist_invoices` unconditionally assigns
`invoice_number`, `invoice_date`, `currency`, `total`, `tax` and `raw_json` on
every re-sync, and refreshes the connector's lines the same way. Any correction
written over those columns is erased by the next run.

A third motivation is new: a human's corrected value is the **label** for a field
the extractor got wrong. Verification is not only a review affordance, it is the
supervision signal for the extraction model. That is why verification is a
distinct action rather than a flag on an edit — the dataset needs to know that a
human looked at a field and left it alone, which an ordinary PATCH cannot express.

Constraints carried in from the existing design:

- `Vendor` is a **global** catalog with no tenant scope. Nothing may write through
  to it from a tenant-scoped surface.
- `web_api` never imports `ai_api`; `ai_api` imports the domain from `web_api`.
  Shared rules (documents, audit, rollup) live in `web_api`.
- FX figures are cleared, never recomputed inline, when their inputs change.
- `spend_categories` and their materialized paths are written only through
  `web_api/spend_trees/service.py` — untouched by this change.

## Goals / Non-Goals

**Goals:**

- Every parsed invoice header field and every descriptive/money line field is
  correctable by a management role, whatever the invoice's provenance.
- A correction is applied in place and is fully recoverable from `AuditLog`.
- A human-settled field is never silently overwritten by an automated write.
- Correcting the supplier never mutates data another tenant reads.
- Lines can be added and deleted, so a stand-in line can be split into what was
  actually bought.
- A broken reconciliation is loudly visible and never blocks a save.

**Non-Goals:**

- A labelled-data **export** endpoint. `verified_fields` + `AuditLog` hold
  everything a dataset builder needs; how it is shaped and served is its own
  change.
- Editing `ErpEntry` postings. They stay flat evidence — this change does not
  touch that rule.
- Editing the spend category through the new line PATCH. Categories go through
  verify, which resolves them against the company's tree; a second write path
  would reintroduce exactly the free-text problem the tree selector removed.
- Retiring `Invoice.source`. It stops gating writes but stays as provenance,
  which is still what tells a reviewer how much to trust a value.
- Automatic re-categorization after a description correction. A corrected
  description is better input for the categorizer, but requeuing is a separate
  decision with its own cost model.

## Decisions

### 1. In-place edits with a per-field verification record — not a shadow column set

**Decision.** Corrections overwrite the stored column. `Invoice.verified_fields`
and `InvoiceLine.verified_fields` (JSON arrays of field names) record what a
human settled. `AuditLog` holds the prior values.

**Alternative considered — `corrected_*` columns beside the posted ones.** This
matches the strongest precedent in the codebase (`document_invoice_number` beside
`invoice_number`, `base_total` beside `total`) and keeps the ERP value on the
row. It was rejected because it doubles the width of the money columns, forces
every reader — reports, exports, the categorizer, the reconciler — to know about
a coalesce, and creates two ways for a figure to be wrong. The audit trail
already provides recoverability; a second storage location for the same fact
provides mainly a way for them to disagree.

**Why per field, not per row.** A row-level "verified" boolean would freeze an
invoice against the ERP entirely: a reviewer who corrects a typo'd invoice number
would also stop a genuine later re-posting of the total from reaching us. A field
list keeps the sync doing its job everywhere a human has not spoken.

**Storage shape.** JSON array of field-name strings, defaulting to `[]`. Not a
join table: the list is small, always read with its row, never queried across
rows, and a table would add a join to every invoice read for no gain. Order is
not significant; writes normalize by sorting so diffs stay deterministic.

### 2. The sync consults `verified_fields`; `--hard-reset` is the only override

**Decision.** `_persist_invoices` gains a small helper — `assign_unverified(row,
field, value)` — replacing the bare `row.x = ...` assignments. It skips a field
listed in `row.verified_fields`. `run_sync(hard_reset=False)` and a
`--hard-reset` CLI flag flip it to assign regardless, audit each overwrite with
actor `system`, and drop the overwritten names from `verified_fields`.

**Why the helper rather than a dict-diff at the end.** The assignments are
already explicit and readable; a helper keeps the skip rule visible at each site
instead of hiding it in a post-processing pass that a future field addition would
silently bypass.

**Human lines are skipped structurally, not by field list.** A line with
`origin == 'human'` was never produced by the connector, so the connector's
line loop cannot address it: it keys lines by `_det_id("line", invoice_id,
line_erp_id or idx)`, and a human line's id is a fresh UUID that no connector key
can collide with. The rule is therefore already true by construction; the change
adds a test asserting it rather than new logic.

**Hard reset does not delete human lines.** It restores field values; it is not a
"drop everything the customer did" button. Removing a human line is a delete the
customer performs themselves.

### 3. `POST /invoices/{id}/verify` mirrors the line verify endpoint

**Decision.** Same shape as `POST /invoice-lines/{id}/verify`: optional body of
corrections, applied then marked verified, audited, one transaction,
management-gated, `404` outside scope. `action` is `edit` when `diff_changes`
returns anything and `verify` when it does not.

Verified fields are the union of the previously verified set and the fields the
caller **sent** (`model_dump(exclude_unset=True)`), not just the ones that
changed — sending `total: 2400` when the stored value is already `2400` is a
human asserting that figure is right, which is precisely the label a
resubmission must still capture. The audit action is `verify` in that case, not
`edit` — a verification happened and nothing was corrected; `noop` stays the
*PATCH* vocabulary for "you asked me to change something and nothing changed".
The two records answer different questions.

**Alternative considered — a `verified: true` field on the existing PATCH.**
Rejected: verification stops being a distinct auditable action, and the "accept
the parse unchanged" case (an empty body) becomes indistinguishable from an
empty PATCH.

**Symmetry with lines.** The line verify endpoint gains the same
`verified_fields` bookkeeping, so both surfaces produce labels the same way.

### 4. Supplier corrections are invoice-scoped overrides, never a vendor write

**Decision.** `Invoice` gains `supplier_name`, `supplier_country_code`,
`supplier_vat_number`, all nullable, all meaning "no correction" when null.
`InvoiceRead` resolves each as `override ?? vendor.value` and carries a
`supplier_overrides: list[str]` naming which of the three are overridden, so the
UI can mark a corrected value without a second request. `vendor_id` remains
directly settable, validated to an existing vendor (`422` otherwise).

**Why not write the `Vendor` row.** It is global and shared: one org correcting a
supplier's country would rewrite it for every other org, silently. That is a data
leak in the direction of corruption, and no permission check on the invoice
endpoint can fix it.

**Why not per-invoice only, dropping the re-point.** The two corrections answer
different questions — "this is the wrong supplier" versus "this supplier's
details are wrong on this document" — and only the re-point fixes vendor-level
spend aggregation, which reads `Invoice.vendor_id`.

**Consequence, accepted.** `/reports/spend-by-vendor` continues to group by
`vendor_id`, so a name override does not move spend between vendors. Correct: an
override says the *document* named the supplier differently, not that the spend
belongs elsewhere. Moving it is what the re-point is for.

### 5. Line writes are three endpoints, and the category stays on verify

**Decision.** `PATCH /invoice-lines/{id}` (descriptive + amount fields), `POST
/invoices/{id}/lines` (create), `DELETE /invoice-lines/{id}`. A PATCH naming any
categorization field or `native_account_code` is `422` — Pydantic `extra="forbid"`
plus explicit rejection, so the failure is a clear message rather than a silently
ignored field.

**Delete is hard, with an audit row carrying the line's values**, following the
`superseded_by_extraction` precedent in `ai_api/documents/replace.py`: the removed
line's categorization is written to the audit trail and referencing entries have
`source_invoice_line_id` set to NULL. A soft-delete flag was rejected because
every reader — reports, the categorizer, the reconciler, the entry payload's
category resolution — would need to learn to exclude it, and the audit row
already preserves the record.

**A created line's origin is `human`**, a new `LineOrigin` member with the highest
precedence. This is what makes "a sync never displaces it" a statable rule rather
than an accident of id generation, and what lets the UI mark it honestly.

**The one-origin-per-invoice rule is relaxed for `human` only.** A reviewer
splitting a stand-in works incrementally — add two lines, then delete the
stand-in — and a storage rule forbidding the intermediate state would make the
operation impossible without a bulk "replace all lines" endpoint nobody asked
for. The reconciliation warning covers the intermediate state instead, which is
exactly what it is for.

### 6. Reconciliation: computed on read, warned not enforced

**Decision.** The tolerance rule moves out of `ai_api/documents/reconcile.py`
into `web_api` (the domain both callers may import — `ai_api` imports `web_api`,
never the reverse) and is used by both the extraction accept/reject decision and
a new `lines_reconciled` / `reconciliation_delta` pair on `InvoiceDetailRead`.

Computed on read, never stored: it is a pure function of the lines and the header,
both of which this change makes mutable from several endpoints, and a stored flag
would have to be recomputed at each of them. The same reasoning that keeps
`category_stale` computed.

**Delta definition.** Signed `sum(lines.amount) − nearest_accepted_total`, where
the accepted totals are `total` and `total − tax`, and "nearest" is by absolute
difference. Signed so the UI can say which way it is out. Null when reconciled,
and null when the invoice has no `total` — an unknown total is not a mismatch.

**Warn, never block**, per the product decision: a reviewer mid-way through a
multi-line correction would otherwise be blocked by their own unfinished work,
and the ERP's total may itself be the wrong figure. The extraction stage keeps
rejecting — a model producing lines that do not add up has no reviewer standing
behind them.

### 7. FX clearing extends to lines, unchanged in kind

Correcting `currency`/`total`/`tax` already nulls the invoice's base figures.
Correcting a line's `amount` now nulls that line's `base_currency`,
`base_amount`, `fx_rate`, `fx_rate_date` by the same rule and for the same
reason, and the cleared fields ride in the same audit diff. No inline conversion
is added at any of these endpoints. `POST /companies/{id}/recompute-fx` remains
the way back.

### 8. Document extraction yields to verified lines — only automatically

`_queue_document` skips an invoice whose lines include a `verified` or `human`
one. An explicit `POST /invoices/{id}/reprocess` still proceeds and still
replaces, because it is a human decision and the per-line audit rows are the
record. This preserves "extraction wins" where a human asked for it and removes
it where nobody did.

### 9. Frontend: the editors already exist; the gate and the field set change

`EditableInvoiceHeader` becomes the default rather than the `pdf_extraction`
branch, gated on role instead of source, and grows currency, the vendor picker
(a searchable selector over `GET /vendors`, matching the tree selector's
"chosen, never typed" rule) and the three supplier fields (country from the
existing `lib/countries.ts` list). `ReadOnlyField` survives for the read-only
role — a `viewer` gets text, never a disabled input.

`LineCategoryEditor` grows the descriptive/amount inputs beside its category
selector, keeping its `key={line.id}` remount discipline. Add/delete controls and
the reconciliation banner live on `VoucherLinesTab`, with the mismatch also
surfaced in the drawer header so a reviewer on the Details tab cannot miss it.

## Risks / Trade-offs

- **The ERP's original value now lives only in `AuditLog`.** → The audit write is
  in the same transaction as every correction; a test asserts the `old` value is
  present for each correctable field. `AuditLog` is append-only by requirement,
  and `--hard-reset` gives an operational path back to the ERP's figures.

- **A verified field silently diverging from a genuinely re-posted ERP value.**
  A voucher legitimately re-posted in the ERP will not reach a field a human
  settled, and nothing currently tells them. → Accepted for this change, and
  narrowed by being per field. A follow-up can record "the ERP now states X" as a
  conflict without changing the storage model, since the sync already sees both
  values at the assignment site.

- **Line add/delete makes a voucher's lines diverge from its postings.** →
  Deliberate: the lines are what was bought, the postings are how it was booked,
  and the product already accepts that a voucher's Total Spend need not equal the
  sum of its lines. The reconciliation warning makes divergence from the *invoice
  total* visible, which is the one that indicates an error.

- **`extra="forbid"` on the line PATCH will break a client that sends a full line
  object back.** → The frontend sends only changed fields already
  (`toInvoiceUpdate`'s pattern); the same pattern is used for lines. The
  strictness is worth it: a silently-ignored `spend_category_id` would look like
  a category edit that did nothing.

- **`verified_fields` as JSON is not queryable per field in SQL.** A future "show
  me every invoice with an unverified total" filter would need a scan or a schema
  change. → No such filter is asked for; the row-level "has any verification"
  question is answerable from `verified_at`.

- **Two ways to reach an invoice's lines (verify for category, PATCH for the
  rest) is a seam a client can get wrong.** → The `422` on a category field in
  PATCH makes the mistake loud, and the frontend routes both through one editor
  component that knows which call each field belongs to.

## Migration Plan

1. **Schema** — one Alembic revision on top of the current head adding
   `invoices.supplier_name`, `supplier_country_code`, `supplier_vat_number`,
   `verified_fields`, `verified_at`, `verified_by`, and
   `invoice_lines.verified_fields`. All nullable or defaulted; `verified_fields`
   defaults to `[]` server-side so existing rows read as unverified without a
   backfill. No column is dropped and no data is rewritten, so the revision is
   reversible and safe to deploy ahead of the API.
2. **API** — deploy the endpoints. The removed `409` is a widening: no existing
   client breaks, since none could reach a `pdf_extraction` invoice anyway.
3. **Sync** — deploy the verified-aware `_persist_invoices`. With no verified
   rows yet, behaviour is byte-for-byte what it is today until the first
   verification.
4. **Frontend** — ship the editors last, so the API they depend on is already
   live.

**Rollback.** Revert the API and frontend; leave the columns. A reverted API
stops honouring `verified_fields`, which means the sync resumes overwriting —
recoverable from the audit trail, and the columns keep their data for a
re-deploy. Only if the change is abandoned outright is the schema revision
downgraded.

## Open Questions

- Should a description correction requeue the line for categorization? A better
  description is better input, but re-running the categorizer over a line a human
  just touched risks overwriting a category they were about to verify. Deferred:
  today the reviewer can re-verify by hand, and the answer likely depends on how
  the embedding categorizer behaves.
- Should `GET /invoices` gain a `verified` filter so a reviewer can work the
  unverified backlog, as `stale=true` does for categories? Not required by the
  ask; `verified_at` makes it cheap to add later.
- What consumes the labels? The dataset shape (parsed value vs. human value, per
  field, with the document reference) is deliberately out of scope here — this
  change only guarantees the signal is captured and recoverable.
