## Context

Today the Entries page is a ledger viewer. `GET /erp-entries/vouchers` groups
`ErpEntry` rows by voucher, the table expands a voucher into its postings, and
each posting borrows a spend category from the `InvoiceLine` it was posted from
(`ErpEntry.source_invoice_line_id`). That link already exists, and it is already
derived rather than matched — the sync rebuilds the line id from the same
`(invoice, line_erp_id)` pair `_persist_invoices` used.

Where the lines come from today depends entirely on the connector. Billy supplies
`billLines`, which are accounting lines — an account, an amount, a memo. They are
very nearly the postings again. Nothing in the system has ever opened the
attached document, even though the sync already records a `File` for it and
`GET /invoices/{id}/document` already streams it live from the ERP.

So the categorizer has been categorizing bookkeeping memos. That is enough to say
"this voucher was IT spend" and nothing more — not which monitor, not from which
supplier at what unit price, which is what redundancy detection and product-level
savings need.

The constraints that shape the design:

- `web_api` must not import `ai_api`. The stage lives in `ai_api`; the status
  fields and the reprocess endpoint live in `web_api`.
- The domain already has exactly one categorizable unit (`InvoiceLine`), one
  audit table, one rollup, and one FX conversion path. This change must reuse
  all four rather than grow parallel ones.
- The sync runner discovers its work from the database and isolates failure per
  integration. The new stage should be recognisably the same shape, for the same
  reasons.
- The connector contract already exposes `fetch_invoice_document`. No connector
  changes are needed.

## Goals / Non-Goals

**Goals:**

- Make `InvoiceLine` the unit the Entries page shows and the unit the AI
  produces, with the voucher retained as the grouping and the ledger retained as
  evidence.
- Turn each invoice's attached document into lines, out of band, without the
  ledger sync ever waiting on an LLM.
- Guarantee that every voucher with spend has lines, whether or not a document
  exists, so categorization and the reports never go dark.
- Make the difference between "we read the document" and "we assumed the posting"
  a stored, visible property rather than something a reader has to infer.

**Non-Goals:**

- Improving the categorizer. It runs unchanged; it simply gets better input.
- A queue, worker pool or message broker. The stage is a cron-shaped process
  like the sync runner.
- Line-level matching between extracted lines and postings. We do not attempt it,
  and the spec says why.
- A human affordance to lock a line against replacement. Verification on this
  platform is not yet wired into this flow; the audit record is the groundwork.
- Touching the PDF `InvoiceFlow` entry point (`main.py`). Its extraction agents
  are reused; its CSV ledger output is not.

## Decisions

### The stage is a separate process, not a step in the sync

`python -m ai_api.documents.runner`, discovering `doc_status = 'pending'`
invoices from the database exactly as `run_sync()` discovers connected
integrations.

*Why:* the sync's job is to land the ledger and advance a watermark. Extraction
is per-invoice, LLM-bound, and fails for reasons that have nothing to do with the
ERP. Inlining it would mean an LLM outage stalls the ledger, a sync run's
duration becomes a function of invoice count, and a failure has to decide whether
to advance the watermark. Separating them makes each failure mode local:
`_sync_one` already isolates per integration, and the new stage isolates per
invoice.

*Alternative considered:* a `--with-documents` flag on the sync runner. Rejected —
it makes one process have two failure budgets and two natural cadences (the
ledger wants frequent, extraction wants whenever there is a backlog).

### Claim-before-work, via `doc_status = 'processing'`

The stage moves an invoice to `processing` in its own committed transaction
before fetching anything.

*Why:* two overlapping runs — a cron overlapping its predecessor is the ordinary
way this happens — would otherwise both extract the same invoice, and the second
replacement would fire against lines the first had already replaced. This is a
lightweight lease, not a lock; a process that dies mid-work leaves an invoice
stuck in `processing`, which the retrigger endpoint and a stale-claim sweep on
`doc_processed_at` both resolve.

*Alternative considered:* a row lock held for the duration of the extraction.
Rejected — it holds a database transaction open across an LLM call.

### Precedence is `document_ai` > `erp` > `entry_fallback`

`InvoiceLine.origin` is stored, not inferred, and an invoice holds exactly one
origin at a time.

*Why:* the three sources describe the same spend, so mixing them double-counts an
invoice. Stored rather than inferred because a stand-in line and an extracted
line can be byte-identical in description and amount — the difference is entirely
about whether anyone read the document, which is not recoverable from the values.
The ordering follows evidence quality: the document knows what was bought, the
ERP's bill lines are its own statement of the voucher, a posting is the floor.

The user's framing was "entry == invoice line" as the fallback. Keeping `erp`
above `entry_fallback` preserves today's behaviour for connectors that do supply
lines, and costs nothing: for Billy the two are nearly the same rows anyway.

### Replacement is whole-invoice, in one transaction, and audited

On a successful extraction: delete the invoice's `erp`/`entry_fallback` lines,
null the `source_invoice_line_id` of any posting that referenced them, insert the
`document_ai` lines, recompute the rollup — all in one transaction, with an
`AuditLog` row per removed line.

*Why whole-invoice:* a partial replacement leaves an invoice describing its spend
twice.

*Why null the posting links:* an extracted line has no ERP line identity. The
only way to relink would be to match on amount or description, which is exactly
the guessing the current design refuses — the existing spec already says the link
is derived, never matched. The visible consequence is that a posting on an
extracted invoice shows no spend category on the Postings tab. That is acceptable
now precisely because the category has moved to where the reader is looking: the
Lines tab and the expanded table.

*Why audited:* it is the only record that a human's verified category ever
existed. Per the answer that verification is a platform-level feature not yet in
this flow, extraction wins outright today; the audit row is what a future
lock-a-line affordance would be built on.

### An extraction that does not reconcile is rejected

Sum the extracted lines and compare against `Invoice.total` and against
`total − tax`. Accept if either reconciles within tolerance
(`max(1% × |total|, one currency unit)`, configurable); otherwise record
`failed` with both sums and keep the existing lines.

*Why:* an extraction that misses a line is worse than no extraction. It would be
categorized, aggregated and surfaced as a savings opportunity, and nothing
downstream could tell it was wrong. The ledger total is authoritative and free,
so we use it as a checksum.

*Why both gross and net:* documents state lines with or without VAT and there is
no reliable signal which. `ErpAccount.with_vat` describes the account, not the
document, so it cannot decide this. Trying both is a two-line check that avoids a
large class of false rejections.

*Alternative considered:* accept the lines and flag the discrepancy. Rejected —
a flag nobody acts on means wrong lines flow into the reports anyway.

### Reuse the existing extraction agents; store no bytes

The stage fetches through the connector at processing time (the same path
`GET /invoices/{id}/document` uses) and dispatches on the payload's media type,
routing PDFs through `pdf_loader.py` and images through a vision-capable
extraction path.

*Why no local copy:* there is one scan and it lives in the ERP. A second copy is
a copy to keep in sync, and the document route already established this rule.

*Why media-type dispatch matters here:* Billy attachments are frequently phone
photos of receipts. Handing a JPEG to a PDF parser is the failure the frontend
already learned to avoid, and the stage would otherwise record a confusing
"invalid PDF structure" against a perfectly good document.

### The API carries lines on the voucher, not on a second request

`VoucherGroupRead` and `VoucherDetailRead` gain a `lines` array and the invoice's
`doc_status`/`doc_error`, built through the same `_entry_select()` /
`_entry_read()` / `_entry_conditions()` trio that already keeps the flat list,
the groups and the detail endpoint from drifting apart.

*Why:* the table renders lines on expand. A request per expanded voucher would
make the page's cost a function of how much the user explores, and the panel's
header total already comes from the server for the same reason.

*What does not change:* which vouchers are returned, their grouping, their
pagination, and their amount. `_voucher_amount()` stays the net of expense
postings. The lines are additive payload.

## Risks / Trade-offs

- **Extraction quality is unproven against real documents** → The reconciliation
  check is the gate: a bad extraction fails closed and the stand-in lines stand.
  Benchmark against `ai_api/synthdata` ground truth before pointing it at Billy.
- **Postings lose their category display on extracted invoices** → Accepted and
  specified. The category now lives on the line, which is what the page lists;
  the Postings tab is ledger evidence.
- **An invoice can strand in `processing` if the stage dies** → The retrigger
  endpoint clears it manually; a stale-claim sweep (a `processing` invoice whose
  claim is older than a configured age returns to `pending`) makes it automatic.
- **Replacement discards a human's verified category** → Recorded in the audit
  log, and called out in the spec as the deliberate consequence of not yet having
  a platform verification model. Worth revisiting the moment that model exists.
- **Cost and rate limits: one LLM call and one ERP download per invoice** →
  `--limit` bounds a run; attempts are capped so a permanently bad document is
  not retried forever; the connector's existing 429 handling carries
  `retry_after`.
- **Stand-in lines change what the reports say** → They do not change the
  *totals* (a stand-in line carries the posting's own amount), only the category
  distribution, which was previously derived from the same memo text. The change
  is that lines now exist where before an invoice with no ERP lines had none.
- **Two-origin invoices would double-count** → Enforced at write time in both
  writers (the sync's stand-in upsert and the stage's replacement), and stated as
  a domain requirement so a third writer cannot quietly break it.

## Migration Plan

1. **Schema** — one Alembic revision on `0001_baseline_schema`:
   `invoice_lines.origin` (not null, default `'erp'`);
   `invoices.doc_status` (not null, default `'not_applicable'`), `doc_attempts`
   (not null, default 0), `doc_error`, `doc_processed_at`. Backfill in the same
   revision: every existing line to `'erp'`; every invoice with a `file_id` to
   `'pending'`, the rest to `'not_applicable'`. Index `invoices(doc_status,
   invoice_date)` for the stage's discovery query and
   `invoice_lines(invoice_id, origin)`.
2. **API and sync first, stage second.** Ship the status fields, the payload
   changes and the stand-in materialization before the extraction stage. The
   page becomes line-based immediately, on stand-in lines, and is correct on its
   own — the stage then upgrades vouchers one at a time as it drains the backlog.
3. **Frontend follows the API.** The expanded-row renderer and the Postings tab
   land together; the provenance mark and the retrigger action can follow.
4. **Backfill runs itself.** The migration queues every invoice with a document;
   the first stage run drains it. `--limit` paces it.
5. **Rollback.** The stage is a separate process — stopping it stops all
   extraction with no effect on the sync or the API. Reverting the frontend
   restores the posting-based table against unchanged API data. The schema
   revision is additive and downgradable; lines already replaced by extraction
   are not restored by a downgrade, which is why step 2 ships before step 3 and
   the stage is run against a single company first.

## Open Questions

- **Which extractor reads an image?** `flow.py`'s agents assume text from
  `pdf_loader.py`. A vision model is needed for photographed receipts, and the
  local vLLM `gemma-4-E4B-it` deployment may or may not serve one. Until it does,
  images record a clean unsupported-media failure and keep their stand-in lines.
- **What cadence does the stage run on, and where?** It is a second scheduled
  process; deployment currently has one.
- **Does a stale `processing` claim sweep automatically in the first cut, or is
  the retrigger endpoint enough?** Automatic is a few lines and removes an
  operational chore; it is listed under risks rather than specified.
- **Should `spend-by-vendor` and `spend-by-category` expose the origin mix?**
  A report whose categories come from stand-in lines is less trustworthy than one
  from extracted lines, and the reader currently cannot tell.
