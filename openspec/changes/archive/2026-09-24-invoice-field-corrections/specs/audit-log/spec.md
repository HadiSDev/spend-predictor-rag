## ADDED Requirements

### Requirement: Corrections to parsed invoice data are fully audited

Every correctable invoice and line field SHALL be covered by the audit trail.
Because corrections are applied in place, over the ERP's or the extractor's own
value, the audit trail is the **only** record of what was originally stated.

- The audited invoice field set SHALL cover `invoice_number`, `invoice_date`,
  `currency`, `total`, `tax`, `vendor_id`, `supplier_name`,
  `supplier_country_code` and `supplier_vat_number`, plus the base/FX fields
  cleared as a consequence.
- The audited line field set SHALL cover `description`, `quantity`, `unit`,
  `unit_price` and `amount`, plus the line's base/FX fields cleared as a
  consequence, in addition to the categorization fields already audited.
- A request that changes nothing SHALL be recorded as `noop`, never as an `edit`
  — the feed must not show a change that did not happen.

#### Scenario: A corrected total is recoverable

- **WHEN** a manager changes an invoice's total from the ERP's figure
- **THEN** an audit entry carries the ERP's figure as `old` and the correction as
  `new`

#### Scenario: A cleared conversion is in the same entry

- **WHEN** a correction to a line's amount clears its base amount
- **THEN** one audit entry carries both the amount change and the cleared base
  fields

#### Scenario: An unchanged submission is a noop

- **WHEN** a correction resubmits the values already stored
- **THEN** the audit action is `noop`

### Requirement: Verification, line creation and line deletion are audit actions

The `invoice` and `invoice_line` entities SHALL support the actions `verify`,
`line_added` and `line_deleted` alongside the existing `ai_categorize`, `edit`
and `noop`.

- `verify` SHALL be recorded on the `invoice` entity when a human accepts the
  parsed header without changing a value; a verification that also corrects SHALL
  be recorded as `edit`.
- `line_added` SHALL be recorded on the `invoice` entity, naming the created
  line, so an invoice's own history shows its line set changing.
- `line_deleted` SHALL be recorded on both the `invoice_line` entity (carrying
  the deleted line's field values and categorization) and the `invoice` entity,
  since the line's own history becomes unreachable through a row that no longer
  exists.

#### Scenario: A header verification is recorded

- **WHEN** a manager verifies an invoice header without corrections
- **THEN** an audit entry with action `verify` and the user's id as actor is
  appended to the invoice's history

#### Scenario: A deleted line's values survive it

- **WHEN** a manager deletes a line carrying a verified category
- **THEN** an audit entry records the line's description, amount and
  categorization

#### Scenario: The invoice's history shows the line change

- **WHEN** a line is added and another deleted
- **THEN** the invoice's audit feed carries a `line_added` and a `line_deleted`
  entry, in order

### Requirement: A hard reset over a verified value is attributed to the system

A `--hard-reset` overwrite of a human-verified field SHALL be audited with actor
`system`, so the human's value remains recoverable exactly as the ERP's is after
a correction.

#### Scenario: The overwrite is recorded

- **WHEN** `--hard-reset` replaces a verified total with the ERP's
- **THEN** an audit entry with actor `system` carries the human's value as `old`
  and the ERP's as `new`
