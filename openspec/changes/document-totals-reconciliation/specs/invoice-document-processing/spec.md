## MODIFIED Requirements

### Requirement: An extraction that does not reconcile with the ledger is rejected

The stage SHALL judge an extraction by **two separate checks**, because "did we
read this document correctly?" and "do the supplier and the bookkeeper agree?"
are different questions and only the first has an exact answer.

**Check 1 — the document against itself.** When the document states its own
total, the sum of the extracted lines SHALL be compared against that figure, in
the document's own VAT convention. Failing it means the reading is wrong — a
missed line, a misread column — and the extraction SHALL be **rejected**.

**Check 2 — the document against the ledger.** The document's stated total SHALL
then be compared against the invoice's posted `total`. A disagreement SHALL
**NOT** reject the extraction: the lines are accepted, both figures are stored,
and the disagreement is recorded for a reviewer. A document that adds up is one
we read correctly, and if the ledger says something else that is precisely what a
human should be shown — rejecting means they never see the lines and cannot tell
a misreading from a mis-posting.

**When the document states no total**, the previous rule stands unchanged: the
lines are compared against the invoice's `total` and its `total − tax`, and
reconciling with neither is a rejection.

- A rejected extraction SHALL record `failed` with a reason naming both sums,
  and the invoice's existing lines SHALL stand. Lines that do not add up to the
  document they came from are wrong, and wrong lines would be categorized,
  reported and acted on.
- Both the gross and the net comparison SHALL be tried wherever the convention is
  not stated, because a document may print its lines with or without VAT and the
  ERP's own `with_vat` flag describes the account, not the document.
- The tolerance SHALL be configurable and SHALL be relative as well as absolute,
  so a large invoice is not rejected over rounding and a small one is not
  accepted over a missed line.
- An invoice with no `total` and a document with no stated total SHALL skip both
  checks rather than fail them — there is nothing to reconcile against.

#### Scenario: Lines that add up are accepted

- **WHEN** extraction of a 4.812,00 invoice yields lines summing to 4.812,00
- **THEN** the extraction is accepted

#### Scenario: A document stating lines net of VAT reconciles

- **WHEN** extraction of a 5.000,00 gross invoice carrying 1.000,00 tax yields
  lines summing to 4.000,00
- **THEN** the extraction is accepted against the net figure

#### Scenario: Gross lines against a net-posted total reconcile through the document

- **WHEN** a document prints its lines VAT-inclusive summing to 88,95, states a
  shipping charge of 15,90 and a total of 104,85, and the ERP posted 83,88 with
  no tax
- **THEN** the lines and the shipping charge reconcile against the document's own
  104,85 and the extraction is accepted

#### Scenario: A missed line is rejected

- **WHEN** a document states a total of 4.812,00 and extraction yields lines
  summing to 3.200,00
- **THEN** the extraction is rejected, the invoice reads `failed` with both sums
  in its error, and its previous lines are unchanged

#### Scenario: A ledger disagreement is flagged, not rejected

- **WHEN** the extracted lines reconcile against the document's own stated total
  but that total differs from the invoice's posted `total` beyond tolerance
- **THEN** the lines are written, both totals are stored, and the invoice records
  that its totals disagree

#### Scenario: Rounding does not reject

- **WHEN** extracted lines sum to 4.812,01 against a document stating 4.812,00
- **THEN** the extraction is accepted

#### Scenario: A document with no totals block falls back to the ledger

- **WHEN** the document states no total of its own
- **THEN** the lines are compared against the invoice's `total` and `total − tax`
  as before, and reconciling with neither is a rejection

#### Scenario: Nothing to reconcile against

- **WHEN** the invoice has no `total` and the document states none
- **THEN** both checks are skipped and the extraction is judged only on whether
  it produced lines

## ADDED Requirements

### Requirement: Extraction SHALL read the document's own totals block

Extraction SHALL read what the document states about itself — its total, its tax,
and its net subtotal — and SHALL carry them alongside the lines. Today the totals
block is read past and discarded, which is why the only figure available to
reconcile against belongs to a different system.

The document's figures SHALL be stored **beside** the as-posted ones, which
extraction still never rewrites. That is the rule `document_invoice_number`
already follows, and for the same reason: when the two disagree, the disagreement
is the information, and overwriting either destroys it.

#### Scenario: The document's total is read and kept

- **WHEN** a document states "Total amount EUR 104.85"
- **THEN** the invoice records 104,85 as the document's total and its posted
  `total` is unchanged

#### Scenario: The document's tax is read and kept

- **WHEN** a document states "VAT 25 % EUR 20.97" and the ERP posted no tax
- **THEN** the invoice records 20,97 as the document's tax and its posted `tax`
  remains as the ERP stated it

#### Scenario: A document with no totals block records none

- **WHEN** a document states no totals
- **THEN** the document's total and tax are null, which is distinguishable from
  a stated zero

### Requirement: A line SHALL record the tax figures its document printed

`LineItem` SHALL carry the line's `subtotal` (net of tax), its tax rate, its
`tax_amount` and its `discount` where the document prints them, in addition to
its total.

The rate is the **existing `vat_rate`** field, which is already extracted. The
reference implementation calls the same figure `tax_rate`, and adding that name
alongside would be two fields for one number — the domain column is
`InvoiceLine.tax_rate`, and the extractor's is `LineItem.vat_rate`.

Gross-versus-net SHALL be **read, never inferred**. A document that prints both
figures has both taken, so nothing downstream has to decide which convention a
column follows — which is the guess that rejected a correctly-read invoice whose
line prices were VAT-inclusive and whose posted total was net. The reference
implementation reaches the same shape from the same problem.

Every such field is optional, because every one is genuinely absent somewhere: a
receipt prints one number per line and nothing else.

#### Scenario: A line printing both figures records both

- **WHEN** a line prints a net amount of 29,31 and a gross amount of 36,64
- **THEN** the line records both, and neither is derived from the other

#### Scenario: A line printing one figure records one

- **WHEN** a line prints only a single amount
- **THEN** that amount is the line's total and its tax fields are null

#### Scenario: A stated discount is recorded, not netted away

- **WHEN** a line prints a discount
- **THEN** the discount is recorded as its own figure and the line's total is the
  figure the document printed

### Requirement: A charge stated in the totals block SHALL become a line

Shipping, freight, handling and similar charges printed in a document's totals block SHALL be extracted as **lines**, not discarded.

They are spend: the money left the company, the default tree carries
`Logistics > Shipping` for exactly this, and a charge dropped on the floor is
spend that no report can see. It is also why a correctly-read invoice could not
reconcile — a charge that exists only in the totals block cannot be summed from
any set of line items.

A charge line SHALL be indistinguishable from any other line downstream: it is
categorized, it is reviewable, and a human may correct it. Whether the money was
spent on a product or on getting the product delivered is a categorization
question, not a reason for two kinds of line.

#### Scenario: A shipping charge becomes a line

- **WHEN** a document states "shipping cost incl. VAT EUR 15.90" outside its line
  table
- **THEN** a line is written for it and counts toward the reconciliation sum

#### Scenario: A charge line is ordinary spend

- **WHEN** a shipping charge line is written
- **THEN** it is categorized by the next run like any other line and may be
  corrected by a human

#### Scenario: A discount stated in the totals block is not a charge

- **WHEN** a document states a total-level discount
- **THEN** it is not written as a charge line, since it reduces spend rather than
  being spend
