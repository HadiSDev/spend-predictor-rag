## MODIFIED Requirements

### Requirement: ErpAccount records whether it is with or without VAT

`ErpAccount` SHALL carry a `with_vat` boolean that WE own, recording whether the account is **assumed** to be configured with VAT — seeded from the ERP account when the account is first discovered, and preserved thereafter.

- `with_vat` SHALL be set from the ERP account data when an `ErpAccount` row is
  **created**, since the ERP's value is the best available starting assumption.
- `with_vat` SHALL be **preserved** on every subsequent upsert — neither an
  account refresh nor a re-sync may overwrite it. This applies to every writer of
  `ErpAccount`, not to one code path.
- The value is a customer judgement, not a fact the ERP asserts: some ERPs do not
  report it and the connector defaults it to `false`, which must not be
  re-asserted as truth over a setting the customer has made.
- `with_vat` recomputes no stored amount. It exists so reconciliation can decide
  whether to read invoice lines as including or excluding VAT when comparing a
  predicted total against posted entries — which is what distinguishes a VAT
  difference from a total difference.

#### Scenario: VAT flag is seeded from the ERP account

- **WHEN** an account is discovered for the first time and the ERP reports it as
  with-VAT
- **THEN** the created `ErpAccount` has `with_vat = true`

#### Scenario: Without-VAT account is seeded as such

- **WHEN** an account is discovered for the first time and the ERP reports it as
  without-VAT
- **THEN** the created `ErpAccount` has `with_vat = false`

#### Scenario: A customer's VAT setting survives an account refresh

- **WHEN** a customer sets an account's `with_vat` to the opposite of what the ERP
  reports, and the chart of accounts is then refreshed from the ERP
- **THEN** the account keeps the customer's value while its name, type, parent and
  ERP active state are refreshed

#### Scenario: A customer's VAT setting survives a sync

- **WHEN** a customer sets an account's `with_vat` and the sync pipeline then runs
  and upserts that account
- **THEN** the account keeps the customer's value

### Requirement: ErpAccount has a sync-selection toggle distinct from ERP active state

`ErpAccount` SHALL carry a `sync_enabled` boolean that WE own, controlling whether the sync pulls entries for that account, and it SHALL be distinct from `is_active` (which mirrors the ERP's own active/inactive state).

- `sync_enabled` SHALL default to `true` so a first sync behaves as before.
- `sync_enabled` SHALL be preserved across re-syncs — refreshing an account's
  metadata from the ERP MUST NOT reset a user's selection.
- `is_active` SHALL continue to reflect the ERP's active flag and MUST NOT be
  overloaded as the sync toggle.
- `sync_enabled` is scoped per `ErpAccount`, i.e. per `ErpIntegration` per Company.
- Disabling an account SHALL govern future ingestion only; entries already
  persisted for it SHALL NOT be deleted or hidden by the toggle.

#### Scenario: Disabled account is excluded from entry ingestion

- **WHEN** an `ErpAccount` has `sync_enabled = false`
- **THEN** the sync does not fetch or persist any `ErpEntry` for that account

#### Scenario: Selection survives a re-sync

- **WHEN** an account is toggled `sync_enabled = false` and the ERP accounts are
  fetched again on the next sync
- **THEN** the account's `sync_enabled` stays `false` while its name, type and
  parent metadata are refreshed

#### Scenario: Disabling an account leaves its history intact

- **WHEN** an account with already-synced entries is set to `sync_enabled = false`
- **THEN** its existing `ErpEntry` rows remain, and only future ingestion stops
