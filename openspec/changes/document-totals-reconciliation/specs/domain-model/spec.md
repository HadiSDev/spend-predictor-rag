## ADDED Requirements

### Requirement: An invoice SHALL record what its document stated, beside what the ERP posted

`Invoice` SHALL carry `document_total`, `document_tax` and `document_subtotal` —
the figures printed on the scan — **beside** `total` and `tax`, which the ERP
posted and which extraction never rewrites.

`document_subtotal` is required by the **read** side. `InvoiceDetailRead` has to
reproduce the verdict the extraction stage reached, and without the document's
net figure it would report a gross-printed / net-posted invoice as disagreeing
where the stage said it agreed — the exact drift that keeping one copy of the
rule exists to prevent.

The same rule `document_invoice_number` already follows, and for the same reason.
The two figures come from different systems with different conventions: a German
supplier prints a gross total and a Danish bookkeeper posts the net one, and both
are correct. Overwriting either destroys the only evidence of the other, and when
they genuinely disagree — a typo, a credit applied on one side, a partial posting
— the disagreement is exactly what a reviewer needs.

Both SHALL be nullable, and null SHALL mean "the document stated none",
distinguishable from a stated zero.

#### Scenario: Both figures are kept

- **WHEN** a document states a total of 104,85 and the ERP posted 83,88
- **THEN** the invoice carries both, and neither is derived from or overwritten
  by the other

#### Scenario: Extraction never rewrites the posted total

- **WHEN** extraction reads a total differing from the ERP's
- **THEN** `total` and `tax` are unchanged

#### Scenario: A document stating no total records null

- **WHEN** a document prints no totals block
- **THEN** `document_total` and `document_tax` are null rather than zero

### Requirement: A line SHALL record the tax and discount figures its document printed

`InvoiceLine` SHALL carry `subtotal`, `tax_rate`, `tax_amount` and `discount`,
each nullable, holding what the document printed for that line.

They exist so gross-versus-net is read rather than inferred. A line's `amount`
stays the figure the document printed for it, whichever convention that follows;
these say which convention it was, when the document said.

Null is the ordinary case and SHALL never be defaulted: a posting-derived
stand-in line has no document behind it at all, and a receipt prints one number
per line.

#### Scenario: A line carries what was printed

- **WHEN** a document line prints a net amount, a VAT rate and a gross amount
- **THEN** the line records all three

#### Scenario: A stand-in line carries none of them

- **WHEN** a line is written from a posting rather than a document
- **THEN** its tax and discount fields are null
