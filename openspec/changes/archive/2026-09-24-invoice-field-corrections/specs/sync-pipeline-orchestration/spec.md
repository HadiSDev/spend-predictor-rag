## ADDED Requirements

### Requirement: The runner does not overwrite human-verified fields

`_persist_invoices` SHALL refresh an invoice and its ERP lines from the connector
exactly as it does today, except for the fields a human has verified, which it
SHALL leave untouched.

- The check SHALL be per field, not per row: an invoice with a verified `total`
  SHALL still have its `invoice_date`, `raw_json` and every other unverified
  field refreshed.
- The same rule SHALL apply to `InvoiceLine` rows the connector states.
- A line whose origin is `human` SHALL never be refreshed or removed by a sync —
  the connector has no statement about a line it did not produce.
- Skipping a verified field SHALL NOT change what the run reports as synced, and
  SHALL NOT prevent the watermark advancing.

#### Scenario: A verified total survives a re-sync

- **WHEN** an invoice with a verified `total` is re-synced and the ERP now states
  a different total
- **THEN** the stored total is unchanged and the invoice's other fields are
  refreshed from the ERP

#### Scenario: An unverified field is still refreshed

- **WHEN** an invoice with a verified `total` is re-synced with a new
  `invoice_date`
- **THEN** the stored date is the ERP's new value

#### Scenario: A human line is untouched

- **WHEN** an invoice carrying a human-added line is re-synced
- **THEN** the human line is present and unchanged after the run

### Requirement: A hard reset is the one way to restore the ERP's values

The sync runner SHALL accept a `--hard-reset` flag which overwrites
human-verified fields with the ERP's values.

- It SHALL be opt-in and SHALL never be implied by `--since`,
  `--integration-id`, or any other flag.
- Each overwritten field SHALL be recorded in an `AuditLog` entry with actor
  `system`, so the human's value stays recoverable.
- It SHALL clear the affected rows' verified-field record for the fields it
  overwrote, so the row does not claim to be verified at a value it no longer
  holds.
- It SHALL NOT delete human-added lines.

#### Scenario: A hard reset overwrites and audits

- **WHEN** the runner runs with `--hard-reset` over an invoice with a verified,
  corrected total
- **THEN** the ERP's total is stored, an audit entry with actor `system` records
  the overwrite, and `total` is no longer listed as verified

#### Scenario: Hard reset is never the default

- **WHEN** the runner runs without `--hard-reset`
- **THEN** verified fields are preserved

#### Scenario: Human lines outlive a hard reset

- **WHEN** the runner runs with `--hard-reset` over an invoice with a human-added
  line
- **THEN** the human line is still present
