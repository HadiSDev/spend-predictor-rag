## MODIFIED Requirements

### Requirement: Refresh the account chart from the ERP

The API SHALL expose `POST /api/v1/erp-integrations/{id}/refresh-accounts` that re-fetches the ERP chart of accounts and upserts `ErpAccount` rows, preserving every setting the customer owns.

- New accounts SHALL be inserted, with `with_vat` seeded from the ERP's reported
  value.
- Existing accounts SHALL have their **ERP-owned** metadata refreshed — name,
  type, parent, and `is_active`.
- An existing account's `sync_enabled` **and** `with_vat` SHALL be preserved. Both
  are customer settings; a refresh that reset either would silently discard a
  decision the customer made.
- The response SHALL report how many accounts were seen / added.
- The endpoint SHALL require management authorization and an in-scope integration,
  and SHALL run entirely within `web_api` (no `ai_api` import).

#### Scenario: New ERP accounts are added, selections preserved

- **WHEN** the ERP has gained accounts and an existing account was disabled, then a
  manager refreshes accounts
- **THEN** the new accounts are inserted and the previously disabled account
  remains `sync_enabled = false`

#### Scenario: A customer's VAT setting is not reset by a refresh

- **WHEN** a manager has set an account's `with_vat` to the opposite of the ERP's
  reported value and then refreshes accounts
- **THEN** the account keeps the manager's value while its name and type are
  refreshed from the ERP

#### Scenario: A newly discovered account takes the ERP's VAT value

- **WHEN** a refresh discovers an account the deployment has not seen before
- **THEN** its `with_vat` is set from the ERP's reported value
