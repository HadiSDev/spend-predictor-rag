## ADDED Requirements

### Requirement: ErpAccount has a sync-selection toggle distinct from ERP active state

`ErpAccount` SHALL carry a `sync_enabled` boolean that WE own, controlling whether the sync pulls entries for that account, and it SHALL be distinct from `is_active` (which mirrors the ERP's own active/inactive state).

- `sync_enabled` SHALL default to `true` so a first sync behaves as before.
- `sync_enabled` SHALL be preserved across re-syncs — refreshing an account's
  metadata from the ERP MUST NOT reset a user's selection.
- `is_active` SHALL continue to reflect the ERP's active flag and MUST NOT be
  overloaded as the sync toggle.
- `sync_enabled` is scoped per `ErpAccount`, i.e. per `ErpIntegration` per Company.

#### Scenario: Disabled account is excluded from entry ingestion

- **WHEN** an `ErpAccount` has `sync_enabled = false`
- **THEN** the sync does not fetch or persist any `ErpEntry` for that account

#### Scenario: Selection survives a re-sync

- **WHEN** an account is toggled `sync_enabled = false` and the ERP accounts are
  fetched again on the next sync
- **THEN** the account's `sync_enabled` stays `false` while its name/type/VAT
  metadata are refreshed

### Requirement: ErpAccount records whether it is with or without VAT

`ErpAccount` SHALL carry a `with_vat` boolean, read from the ERP account, recording whether the account is configured with VAT or without VAT.

- `with_vat` SHALL be populated from the ERP account data during account sync.
- `with_vat` is metadata only in this change: no amount is recomputed from it. It
  exists so later categorization can decide whether to sum invoice lines including
  or excluding VAT when reconciling predicted totals against posted entries.

#### Scenario: VAT flag is stored from the ERP account

- **WHEN** the ERP reports an account as with-VAT
- **THEN** the persisted `ErpAccount` has `with_vat = true`

#### Scenario: Without-VAT account is stored as such

- **WHEN** the ERP reports an account as without-VAT
- **THEN** the persisted `ErpAccount` has `with_vat = false`
