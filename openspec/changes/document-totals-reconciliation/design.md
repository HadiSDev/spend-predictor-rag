## Context

`ai_api/documents/` reads an invoice's scan into lines. `web_api/reconcile.py`
owns the rule that decides whether the reading is acceptable, shared with the API
so an extraction accepted as reconciling is never then reported to a reviewer as
not reconciling.

The rule is: **the sum of the extracted lines must equal the invoice's `total`,
or its `total − tax`, within `max(1%, 1.00)`.**

That rule compares *the document's lines* against *the ERP's total*. Two systems,
two VAT conventions, one comparison — and it is failing on documents that are
read perfectly.

**The evidence, verified against the live model and the live document.**
Aquatuning `F10566081` extracts to three correct lines summing to 88,95 and is
rejected against a posted total of 83,88. The document's own totals block:

| line | figure |
| --- | --- |
| Sum with tax | 88,95 |
| shipping cost incl. VAT | 15,90 |
| Total without VAT 25 % | 83,88 |
| VAT 25 % | 20,97 |
| Total amount | 104,85 |

`(88,95 + 15,90) / 1,25 = 83,88`. The document is internally exact. Two things
break the comparison independently:

1. Lines are printed **gross**, the posted total is **net**. `Invoice.tax` is
   `0.00` in Billy, so `total − tax` equals `total` and the rule's second branch
   is a no-op — the "document may state lines net of VAT" allowance never fires.
2. **Shipping has no line.** 15,90 exists only in the totals block, so no set of
   line items can sum to the total.

On the dev ledger **6 of 28 invoices are `failed`, and every one is a
reconciliation refusal**, not a document we could not open or read.

**What `~/repos/groundley-ai` does**, checked before scoping this:

- `LineItem` carries `subtotal`, `tax_rate`, `tax_amount`, `total`, `discount`,
  `discount_rate` — gross-versus-net is **extracted, not inferred**.
- `InvoiceResponse` carries `total_excl_vat`, `total_incl_vat`, `total_vat`.
- **There is no reconciliation gate at all.** `helpers/price_fixer.py` is a
  *repair* pass that distributes invoice VAT proportionally across lines and
  swaps mislabelled gross/net columns. Nothing is ever rejected for not adding up.
- No shipping handling anywhere — a charge is a line only if the model emits one.
- Its page merger concatenates without deduplication, exactly as ours does.

## Goals / Non-Goals

**Goals:**

- A correctly-read document is accepted.
- A misread document is still rejected.
- Shipping and similar charges become spend the reports can see.
- A disagreement between the supplier's figures and the bookkeeper's is
  *recorded and shown*, not resolved by discarding one side.

**Non-Goals:**

- **No `fix_price`-style repair pass.** Groundley redistributes VAT across lines
  and swaps columns it believes are mislabelled; its own source marks two of
  those branches `# questionable`. Rewriting amounts the document printed is the
  opposite of this codebase's rule that numbers are transcribed, not interpreted.
  We extract more fields instead, and let the arithmetic fall out.
- **No removal of the gate.** Groundley has none. A gate pointed at the right
  question is worth keeping: a model that misses a line on a wide table is a real
  failure mode here, and `parse_amount` already turns some of them into a null
  rather than a wrong number.
- **Not the 2× double-count.** `2049,74` against `1024,87` is a different defect,
  control-tested earlier and confirmed pre-existing. The reference implementation
  offers nothing — its merger concatenates like ours — so it needs its own
  investigation against that document.
- **No change to entry-based reporting.** `Invoice.total` is untouched, so
  `entries-summary` and the voucher totals are unaffected throughout.

## Decisions

### 1. Two checks, because there are two questions

```
lines ──sum──▶ compare with document.total        → REJECT on mismatch
document.total ──compare──▶ invoice.total         → FLAG on mismatch
```

The first is arithmetic within one source and has an exact answer: if the lines
do not add up to the total printed on the same page, we misread the page. That is
what rejection is for, and it is *stricter* than today's rule, not weaker — the
tolerance is against a figure from the same document rather than one that may
legitimately differ.

The second has no exact answer. A German supplier printing gross and a Danish
bookkeeper posting net are both correct; a partial posting, a credit note applied
on one side, or a typo are all real and all things a human resolves. **Rejecting
means the reviewer never sees the lines** and cannot tell a misreading from a
mis-posting — which is exactly the position the Aquatuning invoice is in now.

*Alternative rejected — keep one check and widen the tolerance.* It would accept
this document and simultaneously stop catching a genuinely missed line, because
the two errors are the same size. Widening a tolerance to admit a case it was
never shaped for is how a check stops meaning anything.

### 2. Fall back to today's rule when the document states no total

A receipt often prints no totals block. Then the ERP's total is the only figure
there is, and the existing gross-or-net comparison is exactly right. The new path
is an *addition*, not a replacement — which also keeps every existing test
meaningful rather than rewritten.

### 3. Read more fields rather than infer harder

`LineItem` gains `subtotal`, `tax_rate`, `tax_amount`, `discount`.
`ExtractedLines` gains `total`, `tax`, `subtotal`.

This is the reference implementation's answer and it is the right one: the
document usually *says* which convention a column follows, and reading it is
cheaper and more honest than deducing it. Where the document says nothing, the
gross-or-net pair is still tried — inference stays, as the fallback it should
always have been.

Every field is optional. A receipt prints one number per line; a stand-in line
has no document at all.

### 4. A charge is a line, not a special case

Shipping becomes an ordinary `InvoiceLine`. Not a flag, not a separate table, not
an adjustment on the invoice.

The alternative — subtracting known charges from the total before comparing —
was considered and rejected: it makes the reconciliation arithmetic work while
leaving the money invisible. €15,90 of freight is spend. The tree has
`Logistics > Shipping`. A reviewer correcting it, a report counting it and the
categorizer reading it all work with no new concept, because it is not a new
concept.

**Consequence, accepted:** a document whose charges the model does not spot still
fails the internal check. That is correct — it means we did not read the document
completely.

*Deliberately not extended to discounts.* A total-level discount reduces spend
rather than being spend, and a negative line would flow into every report as a
category with negative spend. Out of scope, and stated so.

### 5. Store both totals, compute the verdict

`Invoice.document_total` / `document_tax`, beside `total` / `tax` which
extraction never rewrites — the rule `document_invoice_number` already
establishes. `totals_agree` is **computed on read**, like `category_stale`,
`lines_reconciled` and `needs_review`: the tolerance is a tunable judgement and a
stored verdict would be a snapshot of a setting.

`totals_agree` is **null, not true**, when the document stated no total. "Nothing
to compare" and "compared and agreed" are different, and a client that cannot
tell them apart will present an unread document as a verified one.

### 6. The rule stays in one place

`web_api/reconcile.py` already owns the comparison for both the stage and the
API, so the two cannot disagree about whether an invoice reconciles. The split
rule goes there, and the API's `lines_reconciled` follows it automatically.

### 7. The vision path must carry the new fields or silently lose them

`VisionPage` requires nothing — a page is a fragment. The totals block lives on
the **last** page that states one, exactly as `total` already does, and the new
per-line fields concatenate with their lines. This is the easiest thing in the
change to forget and the hardest to notice afterwards: a text-path document would
carry the fields and a scanned one would not, and the only symptom would be
scanned invoices reconciling worse than text ones.

## Risks / Trade-offs

**Accepting on a cross-source mismatch writes lines that disagree with the
ledger** → The internal check still rejects a genuine misreading; the
disagreement is stored and surfaced rather than smoothed over; `Invoice.total` is
untouched so entry-based reporting is unaffected. The exposure is
`spend-by-category`, which reads lines — and today that same invoice contributes a
stand-in line with no category at all.

**The model may not find the totals block** → Then `document_total` is null and
the current rule applies unchanged. The new path degrades to the old one, which
is the same shape as retrieval degrading to the whole tree.

**A charge line the model invents** → It has to reconcile against the document's
own total, which a fabricated charge breaks. The check that used to reject good
readings now catches this instead.

**More fields is more prompt, and a small local model on a wide table is already
this path's weak point** → The fields are added to the schema, where the reference
implementation puts its guidance, rather than as prose. Measured before and after
on all 28 invoices, not assumed.

**Six failures, one diagnosed cause** → Only the diagnosed one is fixed. All six
are re-run afterwards and the remainder reported, so what is left is measured.

## Migration Plan

1. One migration: `invoices.document_total`, `invoices.document_tax`, and
   `invoice_lines.subtotal` / `tax_rate` / `tax_amount` / `discount`. All
   nullable, no backfill — null means "no document said".
2. Extractor schema and prompt, then the vision page schema and merge.
3. `reconcile.py`: the split rule, with the old rule intact as the no-document
   fallback.
4. Runner: accept-and-flag on a cross-source mismatch.
5. Re-run all six `failed` invoices via `POST /invoices/{id}/reprocess`, and
   re-run the 21 `processed` ones in a **dry run** to confirm none regresses.
   Record both in `results.md`.

**Rollback:** the split rule is one function; reverting it restores the old
behaviour with the new columns simply unread.

## Open Questions

- **Does the local model reliably find a totals block on a scanned page?** The
  text path will; the vision path is the open one, and the answer decides whether
  the fallback carries most scanned documents. Measured in step 5.
- **What tolerance for the internal check?** It should be tighter than the
  cross-source one — same-document arithmetic ought to be near-exact — but the
  right value comes from the 28-invoice run, not from picking now.
- **Do any of the remaining five failures share this cause?** Two look
  shipping-shaped by their gaps (15,07 and 4,34) and are untested. Step 5 answers
  it for all of them at once.
