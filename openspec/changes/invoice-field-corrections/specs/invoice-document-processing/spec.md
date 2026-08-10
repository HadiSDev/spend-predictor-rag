## ADDED Requirements

### Requirement: Automatic extraction does not discard human-verified lines

Whole-invoice line replacement SHALL NOT run automatically over an invoice whose
lines include one a human has verified or added.

- The sync's queueing step SHALL NOT set `doc_status` to `pending` for such an
  invoice when it observes a different document. The invoice keeps its lines and
  its existing `doc_status`.
- An explicit `POST /invoices/{id}/reprocess` SHALL still proceed. A human asking
  for the document to be read again is a decision, and the audit row written for
  every removed line remains the record of what was replaced.
- When replacement does run, a removed line that carried human verification SHALL
  be audited with the same `superseded_by_extraction` action, carrying its
  verified values.

#### Scenario: A new document does not overwrite verified work

- **WHEN** a sync observes a different document on an invoice with a verified
  line
- **THEN** the invoice is not queued and its lines are unchanged

#### Scenario: A human can still ask for a re-read

- **WHEN** a manager calls reprocess on that same invoice
- **THEN** the document is queued, and on success the lines are replaced with an
  audit row per removed line

#### Scenario: Unverified invoices are unaffected

- **WHEN** a sync observes a different document on an invoice with no verified or
  human lines
- **THEN** the invoice is queued exactly as it is today

### Requirement: Reconciliation tolerance is one shared rule

The reconciliation tolerance SHALL be implemented once and used both by the
extraction stage's accept/reject decision and by the invoice payload's
reconciliation report. It is `max(1%, 1.00)` against `total` or `total − tax`,
configured by `DOC_RECONCILE_TOLERANCE_PCT` and `DOC_RECONCILE_TOLERANCE_ABS`.

- The two SHALL NOT hold separate copies of the rule. An extraction accepted as
  reconciling must never be reported to a reviewer as not reconciling.

#### Scenario: The same figures give the same verdict

- **WHEN** an extraction is accepted as reconciling
- **THEN** the invoice's payload reports its lines as reconciled

#### Scenario: Configuration reaches both

- **WHEN** `DOC_RECONCILE_TOLERANCE_PCT` is changed
- **THEN** both the extraction decision and the reported reconciliation state
  follow the new value
