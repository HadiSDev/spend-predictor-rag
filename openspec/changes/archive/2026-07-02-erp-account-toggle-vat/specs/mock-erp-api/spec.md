## ADDED Requirements

### Requirement: Accounts expose a VAT flag

Account payloads from the mock ERP SHALL expose a `withVat` boolean so the connector can populate `ErpAccountData.with_vat`.

- Each account item SHALL include a `withVat` field.
- The generated chart SHALL include both with-VAT and without-VAT accounts so the
  flag is meaningfully exercised.

#### Scenario: Account payload includes the VAT flag

- **WHEN** a client fetches accounts from the mock ERP
- **THEN** each account item includes a boolean `withVat`

### Requirement: Entries endpoint filters by account codes

`GET /api/v1/entries` SHALL accept an optional `accounts` filter and, when present, return only entries whose account is in that set, mirroring the fetch-time account selection.

- The `accounts` parameter SHALL accept a comma-separated list of account codes.
- When `accounts` is omitted, all entries SHALL be returned (subject to
  pagination and any `since` filter).
- The `accounts` filter SHALL compose with the existing pagination and `since`
  contract.

#### Scenario: Entries are filtered to the requested accounts

- **WHEN** a client calls `GET /api/v1/entries?accounts=6010,6020`
- **THEN** every returned entry's account is `6010` or `6020`

#### Scenario: Omitting the filter returns all entries

- **WHEN** a client calls `GET /api/v1/entries` with no `accounts` parameter
- **THEN** entries for all accounts are returned, paginated as before
