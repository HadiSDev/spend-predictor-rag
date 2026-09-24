# Document baseline

28 invoices: 6 failed, 1 not_applicable, 21 processed

| invoice | supplier | doc_status | cur | posted total | posted tax | lines | lines sum | origin |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| eNIRM3KISbOYJZvPUSbeQQ | None | processed | DKK | 85.00 | 0.00 | 1 | 85.00 | document_ai |
| IN—-DK-2026-26952 | None | processed | DKK | 4425.00 | 885.00 | 1 | 3540.00 | document_ai |
| 4 | None | not_applicable | DKK | 100.28 | 20.06 | 1 | 100.28 | erp |
| UA31858409 | None | processed | DKK | 1999.00 | 0.00 | 1 | 1999.00 | document_ai |
| 5 | None | failed | DKK | 353.18 | 70.64 | 1 | 353.18 | erp |
| UA31858401 | None | processed | DKK | 20999.00 | 4199.80 | 2 | 16799.20 | document_ai |
| 5351395 | None | failed | DKK | 538.07 | 107.61 | 3 | 538.07 | document_ai |
| Dg5nqnV9RuJQPGV9rFPYxw | None | processed | DKK | 85.00 | 0.00 | 1 | 85.00 | document_ai |
| DX6QHNWU0001 | None | processed | EUR | 90.00 | 0.00 | 1 | 90.00 | document_ai |
| 12 | None | processed | DKK | 58.00 | 0.00 | 1 | 58.00 | document_ai |
| 11 | None | processed | DKK | 58.00 | 0.00 | 1 | 58.00 | document_ai |
| 13 | None | failed | EUR | 90.30 | 18.06 | 1 | 90.30 | erp |
| 100025691 | None | processed | DKK | 464.24 | 92.85 | 2 | 375.27 | document_ai |
| 2835451 | None | processed | DKK | 4999.00 | 999.80 | 1 | 3999.20 | document_ai |
| 16 | None | failed | EUR | 83.88 | 0.00 | 1 | 83.88 | erp |
| 5601713029 | None | processed | DKK | 200.00 | 0.00 | 1 | 200.00 | document_ai |
| IN68385553 | None | processed | DKK | 67.34 | 0.00 | 1 | 67.35 | document_ai |
| IN68501082 | None | processed | USD | 11.16 | 0.00 | 1 | 11.20 | document_ai |
| 22 | None | processed | DKK | 85.00 | 0.00 | 1 | 85.00 | document_ai |
| DX6QHNWU0002 | None | processed | EUR | 90.00 | 0.00 | 1 | 90.00 | document_ai |
| 2125165980 | None | processed | DKK | 2399.00 | 479.80 | 1 | 1919.20 | document_ai |
| 24 | None | failed | DKK | 769.17 | 0.00 | 1 | 769.17 | erp |
| 28 | None | processed | DKK | 85.00 | 0.00 | 1 | 85.00 | document_ai |
| DX6QHNWU0003 | None | processed | DKK | 672.83 | 0.00 | 1 | 672.80 | document_ai |
| 84614420705 | None | failed | DKK | 1024.87 | 0.00 | 9 | 1024.87 | document_ai |
| 29 | None | processed | DKK | 5780.00 | 0.00 | 1 | 5780.00 | document_ai |
| 35 | None | processed | DKK | 85.00 | 0.00 | 1 | 85.00 | document_ai |
| DX6QHNWU0004 | None | processed | EUR | 90.00 | 0.00 | 1 | 90.00 | document_ai |

## The failures, with the reason each recorded

- **5** (None) — extracted lines sum to 267.76, which matches neither the invoice total 353.18 nor its net-of-VAT 282.54 within 3.5318
- **5351395** (None) — extracted lines sum to 523.0, which matches neither the invoice total 538.07 nor its net-of-VAT 430.46 within 5.3807
- **13** (None) — extracted lines sum to 85.96, which matches neither the invoice total 90.30 nor its net-of-VAT 72.24 within 1.0
- **16** (None) — extracted lines sum to 88.95, which matches neither the invoice total 83.88 nor its net-of-VAT 83.88 within 1.0
- **24** (None) — extracted lines sum to 490.290774000, which matches neither the invoice total 769.17 nor its net-of-VAT 769.17 within 7.6917
- **84614420705** (None) — extracted lines sum to 2049.74, which matches neither the invoice total 1024.87 nor its net-of-VAT 1024.87 within 10.2487

## 1.2 — Does each failure state a totals block?

Answered by fetching the six documents and reading them directly. **Five of the
six are text-layer PDFs**, so this needed no model at all; the sixth is a scan.
`apps/web-api/scripts/doc_baseline.py` produces the table above; the documents themselves
were dumped and read by hand for this section.

**Every one of the six states a totals block.** That was the open question, and
the answer is yes across the board — so the fallback-to-the-ledger path will
carry none of these, and the internal check governs all six.

What that check will say, per document:

| # | supplier | the document's own totals block | why the lines miss it | this change? |
| --- | --- | --- | --- | --- |
| 16 | Aquatuning | `Total amount EUR 104.85` | lines printed **gross** (88.95) + `shipping cost incl. VAT 15.90` stated only in the totals block | **fixed** |
| 24 | Fuluo Flavor | `ALL total(Product+transportation cost) US$113.00` | 15 items at US$5.00 = US$75.00, plus `Transportation US$38.00` stated only in the totals block | **fixed** |
| 5351395 | CompuMail | `Totalbeløb DKK 538.07` | a **table line was missed** — `1 95006 Betalingsmetode (Kortbetaling) 15.07`. 15.07 + 484.00 + 39.00 = 538.07 exactly | no — correctly still rejected |
| 13 | Amazon.de | `Item(s) Subtotal: €90.30`, `Grand Total: €90.30` | the two extracted item prices sum to 85.96, which does not reach the document's **own** subtotal either | no — correctly still rejected |
| 84614420705 | If Skadeforsikring | `Total DKK 1024.87` | the 2× double-count — see below | no — out of scope |
| 5 | AliExpress | one totals block **per order**, not per document | see below | no — different defect |

### Two guesses in `design.md` were wrong, and the documents say so

The design named 15.07 and 4.34 as "shipping-shaped by their gaps ... untested".
Both are now tested and neither is shipping:

* **15.07 is a payment-method fee printed as an ordinary table row**
  (`Betalingsmetode (Kortbetaling)`), which the model simply did not return. The
  document is internally exact and the ledger agrees with it to the øre — so
  after this change its rejection message stops blaming the ledger and starts
  saying the true thing: the lines do not add up to the total printed on the
  same page.
* **4.34 is Amazon's own presentation.** Two item prices (63.97 + 21.99) against
  an `Item(s) Subtotal` of 90.30. The internal check rejects it for the right
  reason where the cross-source check rejected it for the wrong one.

The design's claim that this change fixes *one* diagnosed cause holds. What
changed is which of the remaining five share it: **Fuluo (24) is a second
totals-block-charge case**, matching Aquatuning exactly — items in the table,
freight only in the totals block, and the document stating its own total.

### The 2× double-count is not a page-merge defect

`design.md` and `proposal.md` both record that the reference implementation's
page merger concatenates without deduplication "exactly as ours does", and left
the cause open. The document now says otherwise. Page 3 of the If Skadeforsikring
invoice prints **group headings that carry their group's subtotal**:

```
Ansvarsforsikring                 DKK 550.66      ← heading + subtotal
  Erhvervsansvar                      294.81
  Produktansvar                         9.50
  Ingrediens- og komponentdækning      11.06
  Professionel ansvarsforsikring      229.25
  Skadesforsikringsafgift               6.04      ( = 550.66 )
Personforsikring                  DKK 474.21      ← heading + subtotal
  Arbejdsskadeforsikring              437.81
  Bidrag til Garantifonden             29.75
  Skadesforsikringsafgift Krisehjælp    0.11
  Arbejdsmiljøbidrag                    6.54      ( = 474.21 )
Total DKK                            1024.87
```

550.66 + 474.21 = 1024.87, and the eight components sum to 1024.87 again. The
model returned **both levels**, which is where the exact 2.0× comes from. It is
a group-subtotal row read as a line item — the same shape `_is_summary_row`
handles in the vision path, on a document that takes the **text** path, which
has no such filter. Still out of scope here, but no longer unexplained.

### Invoice 5 is a bundle, not an invoice

The AliExpress PDF is five pages carrying **several separate orders**, each with
its own Summary block (`Subtotal DKK15.39`, `Shipping fee DKK0.02`,
`Total DKK15.39`). There is no single document total for the internal check to
use, and the posting (353.18) is the batch. Two separate problems, neither in
scope:

* the image cap fires — `reading 4 of 5 page(s) — capped at 12 image(s)` — so
  one page's orders are never seen at all;
* even fully read, "the document's own stated total" is not a well-defined
  figure for a multi-order bundle.

### What this predicts

Two of six fixed (16, 24). Three of six still rejected, each with a message that
names the real problem instead of a currency-and-VAT artefact. One (5)
unchanged and out of scope. Measured for real in step 6.
