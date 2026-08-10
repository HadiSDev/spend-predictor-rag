## ADDED Requirements

### Requirement: Invoice header corrections are not gated on provenance

`PATCH /api/v1/invoices/{id}` SHALL accept an invoice whose `source` is `erp`,
and SHALL NOT respond `409 Conflict` on the grounds of provenance.

- The accepted body SHALL be `invoice_number`, `invoice_date`, `currency`,
  `total`, `tax`, `vendor_id`, `supplier_name`, `supplier_country_code` and
  `supplier_vat_number`. Omitted fields SHALL be left untouched; an explicit
  `null` SHALL clear the field.
- The endpoint SHALL remain management-gated.
- A `vendor_id` naming a vendor that does not exist SHALL be rejected `422` with
  nothing written.
- Changing `currency`, `total` or `tax` SHALL continue to clear the invoice's
  stored base amounts, rate and rate date, and the cleared fields SHALL appear in
  the same audit diff.

#### Scenario: An ERP invoice's total is corrected

- **WHEN** a manager PATCHes the total of an invoice with `source` `erp`
- **THEN** the response is `200` and the stored total is the corrected value

#### Scenario: A supplier override is stored on the invoice

- **WHEN** a manager PATCHes `supplier_country_code`
- **THEN** the invoice stores the override and the linked `Vendor` row is
  unchanged

#### Scenario: An unknown vendor is refused

- **WHEN** a manager PATCHes a `vendor_id` that names no vendor
- **THEN** the response is `422` and the invoice is unchanged

#### Scenario: A member cannot correct

- **WHEN** a `member` PATCHes an invoice
- **THEN** the response is `403` and nothing is written

### Requirement: An invoice header can be verified

`POST /api/v1/invoices/{id}/verify` SHALL apply any supplied corrections, mark
the header verified, append an audit entry, and commit in one transaction.

- The body SHALL accept the same fields `PATCH /invoices/{id}` accepts, and SHALL
  be optional — an absent body accepts the parsed values as they stand.
- The response SHALL be the updated invoice, carrying its verified field list,
  verifier and verification time.
- The audit action SHALL be `edit` when a value moved and `verify` otherwise.
- The endpoint SHALL be management-gated and SHALL respond `404` for an invoice
  outside the caller's scope.

#### Scenario: Verifying without corrections

- **WHEN** a manager POSTs verify with no body
- **THEN** the response is `200`, the invoice is marked verified, and the audit
  action is `verify`

#### Scenario: Verifying with a correction

- **WHEN** a manager POSTs verify correcting the invoice date
- **THEN** the date is stored, the audit action is `edit`, and `invoice_date` is
  listed among the invoice's verified fields

#### Scenario: Another tenant's invoice is invisible

- **WHEN** a manager POSTs verify for an invoice belonging to another
  organization
- **THEN** the response is `404` and nothing is written

### Requirement: Line fields can be corrected, added and deleted

The API SHALL expose line-level correction alongside the existing verification of
a line's category.

- `PATCH /api/v1/invoice-lines/{id}` SHALL accept `description`, `quantity`,
  `unit`, `unit_price` and `amount`, apply them in place, and audit the diff. It
  SHALL reject `native_account_code` and any categorization field — a category is
  corrected through verify, which resolves it against the company's tree.
- `POST /api/v1/invoices/{id}/lines` SHALL create a line with those same fields
  plus an optional `sequence`, defaulting to after the invoice's last line, with
  origin `human` and status `uncategorized`.
- `DELETE /api/v1/invoice-lines/{id}` SHALL delete the line, audit the deletion
  with the line's values, and NULL `source_invoice_line_id` on every referencing
  `ErpEntry`.
- All three SHALL be management-gated, SHALL recompute the invoice status rollup
  in the same transaction, and SHALL respond `404` outside the caller's scope.
- Correcting a line's `amount` SHALL clear that line's base amount, rate and rate
  date, and the cleared fields SHALL appear in the same audit diff.

#### Scenario: A line description is corrected

- **WHEN** a manager PATCHes a line's description
- **THEN** the response is `200`, the description is stored, and the audit entry
  carries the diff

#### Scenario: A category cannot be smuggled through PATCH

- **WHEN** a PATCH names `level_2` or `spend_category_id`
- **THEN** the response is `422` and the line is unchanged

#### Scenario: A line is added at the end

- **WHEN** a manager POSTs a line to an invoice that already has three lines and
  sends no `sequence`
- **THEN** the new line is created with sequence after the last, origin `human`,
  status `uncategorized`

#### Scenario: A deleted line's postings survive

- **WHEN** a manager deletes a line referenced by a posting
- **THEN** the line is gone, the posting remains with `source_invoice_line_id`
  NULL, and the deletion is audited

#### Scenario: Deleting the last line updates the rollup

- **WHEN** a manager deletes the only categorized line of an invoice
- **THEN** the invoice's status rollup is recomputed in the same transaction

### Requirement: Invoice and line payloads carry correction state

Read models SHALL expose enough state for a client to render what was corrected
and what still needs review, without a second request.

- `InvoiceRead` and `InvoiceDetailRead` SHALL carry `verified_fields`,
  `verified_at`, `verified_by`, the resolved supplier (`supplier_name`,
  `supplier_country_code`, `supplier_vat_number` — the override when set,
  otherwise the linked vendor's value), and a per-field marker of which supplier
  values are overrides.
- `InvoiceDetailRead` SHALL carry `lines_reconciled` and, when false,
  `reconciliation_delta` — the signed difference between the lines' sum and the
  nearest accepted total.
- `InvoiceLineRead` SHALL carry `verified_fields`, and its `origin` vocabulary
  SHALL include `human`.

#### Scenario: The resolved supplier is served

- **WHEN** an invoice has a supplier country override and a linked vendor with a
  different country
- **THEN** its payload reports the override as the supplier country and marks it
  as overridden

#### Scenario: The mismatch is reported on the detail

- **WHEN** an invoice's lines do not sum to its total beyond tolerance
- **THEN** its detail payload has `lines_reconciled` false and a non-zero
  `reconciliation_delta`

#### Scenario: A human line is identifiable

- **WHEN** a line was added by a human
- **THEN** its payload reports origin `human`
