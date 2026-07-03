## ADDED Requirements

### Requirement: fetch_entries filters by selected account codes

`fetch_entries` SHALL accept an optional set of account codes and, when provided, return only entries whose native account is in that set, so the sync pulls only the selected accounts instead of the whole ledger.

- The signature SHALL be `fetch_entries(since: date | None = None, account_codes:
  set[str] | None = None) -> list[ErpEntryData]`.
- When `account_codes` is `None`, the connector SHALL return entries for all
  accounts (unfiltered), preserving existing behavior.
- When `account_codes` is an empty set, the connector SHALL return no entries.
- Filtering by account SHALL compose with the existing `since` date filter.

#### Scenario: Only selected accounts are returned

- **WHEN** `fetch_entries(account_codes={"6010"})` is called
- **THEN** every returned entry has `erp_account_code == "6010"`

#### Scenario: Empty selection returns nothing

- **WHEN** `fetch_entries(account_codes=set())` is called
- **THEN** no entries are returned

### Requirement: ErpAccountData carries the VAT characteristic

`ErpAccountData` SHALL expose a `with_vat` boolean so the runner can persist whether each ERP account is configured with or without VAT.

- The connector SHALL populate `with_vat` from the ERP account payload.
- `with_vat` SHALL default to a safe value (e.g. `false`) when the ERP omits it.

#### Scenario: Connector maps the VAT flag from the ERP payload

- **WHEN** the ERP account payload marks an account as with-VAT
- **THEN** the mapped `ErpAccountData` has `with_vat = true`
