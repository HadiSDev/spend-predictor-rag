## MODIFIED Requirements

### Requirement: Fetch one invoice with its lines

The API SHALL provide `GET /api/v1/invoices/{invoice_id}` returning the invoice header and its `InvoiceLine` rows, only when the invoice belongs to the caller's organization. Each line SHALL include the raw fields (`description`, `quantity`, `unit_price`, `amount`, `native_account_code`), its `status`, and its `spend_category_id` (the accepted category assignment, null until assigned). The line payload SHALL NOT expose AI prediction output (predicted levels, account snapshot, confidence, rationale, or ground truth); that data lives in the `ai_api`-owned categorization store and is not part of this domain read model.

#### Scenario: Owner fetches invoice detail

- **WHEN** a caller requests an invoice that belongs to their organization
- **THEN** the response includes the invoice header and all of its lines, each
  with its raw fields, `status`, and `spend_category_id`

#### Scenario: Line payload omits AI prediction fields

- **WHEN** a caller fetches an invoice detail whose lines have been categorized
- **THEN** each line exposes `spend_category_id` but no predicted level/account,
  confidence, rationale, or ground-truth fields

#### Scenario: Non-owner cannot fetch another tenant's invoice

- **WHEN** a caller requests an `invoice_id` belonging to a different organization
- **THEN** the API responds `404 Not Found`
