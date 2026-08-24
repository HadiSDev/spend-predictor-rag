## Why

**Extraction is being blamed for reconciliation's rejections.** On the dev
ledger, **6 of 28 invoices** are `doc_status = failed`, and every one is a
reconciliation refusal — not a document we could not read.

The case that surfaced it, verified by re-running the live model against the
document. Aquatuning invoice `F10566081`. The model returned:

```
Aquacomputer Double Protect Ultra can 5000ml   qty=1   36.64
EK Water Blocks EK-CryoFuel Loop Cleaner...    qty=1   31.41
THERMAL HERO ULTRA Wärmeleitpaste - 10g        qty=1   20.90
```

Three lines, correct names, correct amounts, correct invoice number. Rejected:

> *extracted lines sum to 88.95, which matches neither the invoice total 83.88
> nor its net-of-VAT 83.88*

The document's own totals block explains itself completely:

```
Sum with tax             EUR  88.95   ← the three lines, VAT-INCLUSIVE
shipping cost incl. VAT  EUR  15.90
Total without VAT 25 %   EUR  83.88   ← what the ERP posted
VAT 25 %                 EUR  20.97
Total amount             EUR 104.85
```

`(88.95 + 15.90) / 1.25 = 83.88`, exactly. The document is internally perfect.
**Two independent things defeat the rule at once**, and each alone would be
enough:

1. **The printed line prices are gross, the posted total is net.** `Invoice.tax`
   is `0.00` in the ERP — Billy posted the net figure with no VAT row — so the
   rule's `total − tax` branch is *identical to its `total` branch* and the
   "document may state lines net of VAT" allowance buys nothing.
2. **Shipping is a real cost with no line.** €15.90 exists only in the totals
   block, so no set of line items can ever sum to the invoice total.

**The rule compares two different sources against each other.** It asks whether
*the document's lines* add up to *the ERP's total* — two systems, two VAT
conventions, one comparison. That conflates a question with an exact answer ("did
we read this document correctly?") with one that has no exact answer ("do the
supplier and the bookkeeper agree?").

`~/repos/groundley-ai` reached the same conclusions and went further: its line
schema carries `subtotal`, `tax_rate`, `tax_amount` **and** `total` per line, so
gross-versus-net is *extracted* rather than inferred — and it has **no
reconciliation gate at all**, only a `fix_price` repair pass. We keep a gate,
because a gate that fires on real defects is worth having; we stop pointing it at
the wrong question.

## What Changes

**Read what the document says about itself**

- `LineItem` gains `subtotal` (net of tax), `tax_rate`, `tax_amount` and
  `discount`, following the reference implementation. A document that prints both
  figures has both read, so nothing downstream has to guess which convention a
  column follows.
- `ExtractedLines` gains the document's **own** stated `total`, `tax` and
  `subtotal`. It carries only `lines`, `currency` and `invoice_number` today, so
  the totals block is read past and discarded.
- **BREAKING (behavioural):** charges printed in the totals block — shipping,
  handling, freight, surcharges — SHALL become **lines**. They are spend, the
  default tree has `Logistics > Shipping` for them, and today they are thrown
  away. A stated charge is not a rounding difference.

**Reconcile within one source, then compare sources**

- **Check 1 — internal.** Do the document's lines add up to the document's own
  stated total? This is arithmetic on one source and has an exact answer. Failing
  it means we misread the document, which is what rejection is for.
- **Check 2 — cross-source.** Does the document's total match the ERP's? This has
  no exact answer, and per the decision on this change it **accepts the lines and
  flags the disagreement** rather than rejecting. A document that adds up is one
  we read correctly; if the bookkeeper posted something else, that is exactly what
  a reviewer should see. Rejecting means they never see the lines and cannot tell
  a misreading from a mis-posting.
- Where the document states no totals block, the current rule stands unchanged —
  compare the lines against the ERP's `total` or `total − tax`.

**Store and surface the disagreement**

- `Invoice.document_total` and `document_tax`, stored **beside** the as-posted
  `total`/`tax` which extraction still never rewrites — the same rule
  `document_invoice_number` already follows, and for the same reason: when the two
  disagree, the disagreement *is* the information.
- The invoice payload carries a computed `totals_agree`, and the voucher panel
  shows both figures when they differ.

## Capabilities

### New Capabilities

None. This deepens document processing rather than adding a capability: the same
stage, reading more of the same document, judged by a rule that separates two
questions it currently conflates.

### Modified Capabilities

- `invoice-document-processing`: the reconciliation rule splits into an internal
  check that rejects and a cross-source check that flags; extraction reads the
  document's totals block; totals-block charges become lines.
- `domain-model`: `Invoice` gains `document_total`/`document_tax` beside the
  as-posted figures; `InvoiceLine` records a line's own tax figures.
- `web-api-invoice-review`: the invoice payload carries the document's totals and
  whether they agree with the ledger's.
- `frontend-erp-entries`: the voucher panel shows both totals when they disagree.

## Impact

**Code** — `ai_api/documents/extractor.py` (schema + totals block),
`ai_api/documents/vision.py` (the per-page schema and merge must carry the new
fields), `ai_api/documents/reconcile.py` and `web_api/reconcile.py` (the split
rule, shared so the stage and the API cannot disagree), `ai_api/documents/runner.py`
(accept-and-flag), `ai_api/documents/replace.py` (charge lines),
`web_api/db/models/invoice.py` + `invoice_line.py` + one migration,
`web_api/schemas.py`, `frontend/src/components/entries/`.

**Data** — no existing line is rewritten. The six `failed` invoices are re-run
through `POST /invoices/{id}/reprocess`, which resets the attempt count for
exactly this case.

**Scope, and why it stops here** — the diagnosed cause only. One of the six
(`2049.74` against `1024.87`, an exact **2.0×**) is a *different* defect: a
double-count I control-tested earlier and confirmed pre-existing. The reference
implementation offers no answer to it — its page merger concatenates without
deduplication, exactly as ours does — so there is nothing to borrow and it needs
its own investigation against that specific document. Two more of the six fit no
pattern yet. All six are re-run and reported after this lands, so what remains is
measured rather than guessed.

**Risk, stated plainly** — accepting on a cross-source mismatch writes lines that
disagree with the ledger's total, and those lines feed the reports. Three things
bound it: the internal check still rejects a genuine misreading, the disagreement
is stored and surfaced rather than smoothed over, and the invoice's own `total`
is untouched so entry-based reporting is unaffected. The exposure is
`spend-by-category`, which reads lines — and today that same invoice contributes a
stand-in line with no category at all, which is not obviously better.
