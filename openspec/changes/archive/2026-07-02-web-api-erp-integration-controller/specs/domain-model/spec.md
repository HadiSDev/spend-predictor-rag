## ADDED Requirements

### Requirement: ErpCredential stores an integration's connection secrets encrypted

The domain model SHALL include an `ErpCredential` entity holding an `ErpIntegration`'s connection configuration (e.g. base URL, API key) **encrypted at rest**, kept separate from the `ErpIntegration` table.

- `ErpCredential` SHALL reference exactly one `ErpIntegration` (one active
  credential per integration).
- The stored config SHALL be encrypted (not plaintext) and SHALL only be decrypted
  server-side to construct a connector; it SHALL NOT be exposed via any API
  response.
- Fields SHALL include: `id`, `erp_integration_id` (FK → erp_integrations),
  `encrypted_config` (ciphertext), `created_at` (and an update timestamp).

#### Scenario: Credentials persist encrypted, never returned

- **WHEN** an integration is created with credentials
- **THEN** an `ErpCredential` row stores the config as ciphertext, and no API
  response returns the decrypted values

### Requirement: ErpIntegration has a soft-disconnect lifecycle

An `ErpIntegration` SHALL support soft-disconnect via its `disconnected_at` timestamp: a disconnected integration is retained (with its accounts, entries, and sync state) and MAY be reconnected by clearing the timestamp.

- Disconnecting SHALL set `disconnected_at` and MUST NOT delete related
  `ErpAccount`, `ErpEntry`, or `SyncState` rows.
- Reconnecting SHALL clear `disconnected_at`.
- An integration with `disconnected_at` set SHALL be treated as inactive by
  default listings.

#### Scenario: Disconnect retains related data

- **WHEN** an integration is disconnected
- **THEN** `disconnected_at` is set and its `ErpAccount`/`ErpEntry` rows are retained

#### Scenario: Reconnect reactivates

- **WHEN** a disconnected integration is reconnected
- **THEN** `disconnected_at` is null and it appears in default active listings
