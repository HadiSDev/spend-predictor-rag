## ADDED Requirements

### Requirement: An invoice payload SHALL state whether its two totals agree

`InvoiceRead` SHALL carry the document's `document_total` and `document_tax`
alongside the posted `total` and `tax`, plus a computed `totals_agree` saying
whether they reconcile within the configured tolerance.

Computed on read and never stored, for the same reason `category_stale` and
`lines_reconciled` are: the tolerance is a tunable platform judgement, and a
stored flag would be a snapshot of a setting rather than a fact about the
invoice.

`totals_agree` SHALL be null — not true — when the document stated no total.
"Nothing to compare" and "compared and agreed" are different states, and a client
that cannot distinguish them will present an unread document as a verified one.

#### Scenario: Agreement is reported

- **WHEN** a document's total matches the posted total within tolerance
- **THEN** the payload reports `totals_agree` true

#### Scenario: Disagreement is reported without blocking anything

- **WHEN** a document states 104,85 and the ERP posted 90,00
- **THEN** the payload carries both figures and reports `totals_agree` false, and
  the invoice's lines and status are unaffected

#### Scenario: No document total is not agreement

- **WHEN** the document stated no total
- **THEN** `totals_agree` is null

#### Scenario: The flag follows the tolerance, not a column

- **WHEN** the reconciliation tolerance is widened
- **THEN** an invoice that previously disagreed reports agreement without any row
  being rewritten
