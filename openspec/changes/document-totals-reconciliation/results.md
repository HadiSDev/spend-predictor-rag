# Results

Measured against `baseline.md`, which was taken before any code changed.

## What was measured, and what could not be

**The local vLLM deployment on `:8999` was unreachable throughout this work**
(`curl` times out; probed at the start and again at the end). Every task that
needs the model to *re-read a document* is therefore unrun:

| task | status |
| --- | --- |
| 6.1 re-run the six `failed` invoices through `/reprocess` | **blocked** — needs the model |
| 6.2 dry-run the 21 `processed` invoices for regressions | **half done** — see below |
| 6.3 set the internal tolerance from the measured distribution | **blocked** — sized from documents instead |

Nothing was inferred in their place. What follows is either arithmetic over real
documents or a property of the code, and each is labelled.

## The deterministic half of 6.2: no stored row's verdict moved

`reconcile_lines` was run over all 28 invoices' current stored state, after the
change:

```
invoices checked: 28
reconciled:       28
not reconciled:   []
totals_agree:     {None}
```

This is not luck and not a sample. `document_total` is a new column with **no
backfill**, so it is null on every existing row, so every invoice takes the
`stated`-empty branch — the previous rule, byte for byte. **No regression on
stored data is possible**, and the run confirms the code agrees with that
reading.

What genuinely remains untested is *re-extraction*: once the model returns a
document total, those 21 invoices take the internal check instead. That is the
measurement 6.2 asked for and it needs the deployment.

## The six failures, re-analysed against their real documents

Not re-extracted — **read directly**. Five of the six are text-layer PDFs, so
their contents were fetched from Billy and examined without a model. The
predictions below follow from the figures each document prints.

| # | supplier | prediction | why |
| --- | --- | --- | --- |
| 16 | Aquatuning | **accepted** | lines gross 88,95 + shipping 15,90 = 104,85 = the document's own `Total amount`. Pinned as a regression test with these exact figures, verified to fail against the pre-split rule. |
| 24 | Fuluo Flavor | **accepted** | 15 items at US$5,00 = US$75,00 plus `Transportation US$38,00` = the document's `ALL total US$113,00`. A second totals-block-charge case, which the design did not know about. |
| 5351395 | CompuMail | **still rejected, truthfully** | a table row was missed — `Betalingsmetode (Kortbetaling) 15,07`. 15,07 + 484,00 + 39,00 = 538,07 exactly, and the ledger agrees to the øre. The message stops blaming the ledger and says the document was not read completely. |
| 13 | Amazon.de | **still rejected, truthfully** | 63,97 + 21,99 = 85,96 against the document's own `Item(s) Subtotal €90,30`. The lines do not reach a figure printed on the same page. |
| 84614420705 | If Skadeforsikring | **still rejected** | the 2× double-count — now diagnosed, still out of scope. |
| 5 | AliExpress | **still rejected** | a multi-order bundle — see below. |

Predicted: **two of six fixed**, three rejected with a message that names the
real problem, one unchanged. Confirming this is 6.1, and it needs the model.

## Three things the documents settled that the design had guessed

**1. The 15,07 and 4,34 gaps are not shipping.** `design.md` called them
"shipping-shaped by their gaps ... untested". 15,07 is a payment-method fee
printed as an ordinary table row that the model did not return; 4,34 is Amazon's
own presentation of two item prices against its subtotal. Both are reading
failures, and both are now rejected *for that reason* rather than for a
currency-and-VAT artefact.

**2. The 2× double-count is not a page-merge defect.** Both `proposal.md` and
`design.md` recorded that the reference implementation "concatenates without
deduplication, exactly as ours does", and left the cause open. The document says
otherwise: page 3 prints **group headings carrying their group's subtotal**
(`Ansvarsforsikring DKK 550,66`, `Personforsikring DKK 474,21`) above the eight
components that sum to those same figures. The model returned both levels, and
550,66 + 474,21 = 1024,87 = the components' sum. That is the exact 2.0×.

It is the shape `_is_summary_row` already handles — on a document that takes the
**text** path, which has no such filter, and under labels that are not summary
words in any language. **Still out of scope**, per the proposal, but no longer
unexplained, and the fix now has a shape: either the text path grows the same
filter, or the extractor is told that a heading with a subtotal is not a line.

**3. Invoice 5 is a bundle, not an invoice.** Five pages of separate AliExpress
orders, each with its own `Subtotal / Shipping fee / Total`. "The document's own
stated total" is not a well-defined figure for it, and the image cap fires
besides — `reading 4 of 5 page(s) — capped at 12 image(s)` — so one page's
orders are never seen. Two problems, neither in scope, and both now written down.

## The internal tolerance

Set to `max(0.1%, 0.10)` (`DOC_INTERNAL_TOLERANCE_PCT` / `_ABS`), against
`max(1%, 1.00)` for the cross-source comparison.

Sized from the documents rather than from a distribution, because 6.3's
measurement could not run. The evidence: every real document examined is exact
about itself to the øre — Aquatuning `88,95 + 15,90 = 104,85`, CompuMail
`15,07 + 484,00 + 39,00 = 538,07`, Fuluo `US$75 + US$38 = US$113`. The absolute
floor is 0,10 rather than 0,01 only because per-line rounding can drift a cent
per line on a long invoice. **Provisional** — it should be revisited against a
real distribution when the deployment is back.

## Still open

* **6.1 and 6.3** — waiting on the deployment.
* **The 2× double-count** (84614420705) — diagnosed above, out of scope here.
* **Multi-order bundles** (invoice 5) — no single document total exists, and the
  image cap silently drops a page.
* **`Invoice.document_total` is stored in the invoice's currency**, converted at
  the reconciliation's own rate. The document's *printed* figure is not kept.
  That is consistent with how extracted line amounts are already stored, but it
  does mean a EUR document's own total is displayed as DKK.
