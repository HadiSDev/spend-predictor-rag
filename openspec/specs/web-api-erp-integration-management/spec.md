# web-api-erp-integration-management Specification

## Purpose

Tenant-scoped, management-gated endpoints to connect an ERP integration with encrypted credentials, manage its accounts (list/toggle/refresh), test the connection, and soft-disconnect/reconnect — all within `web_api`, never importing `ai_api`.

## Requirements

### Requirement: Create an ERP integration with encrypted credentials

The API SHALL expose `POST /api/v1/erp-integrations` for a manager to connect an ERP integration to a company in their scope, and it SHALL store the supplied credentials encrypted at rest.

- The endpoint SHALL require management authorization (system admin or org
  admin/moderator); other roles SHALL receive 403.
- The target `company_id` MUST be within the caller's scope; otherwise 404.
- `erp_type` MUST be a registered connector type; an unknown type SHALL return
  422 (or 400) rather than persisting.
- Supplied credentials (e.g. `base_url`, `api_key`) SHALL be stored **encrypted**
  (not in plaintext) and SHALL NOT be returned in any response.
- The response SHALL include the integration's non-secret fields and indicate that
  credentials are set (e.g. a `has_credentials` boolean), never the secret values.

#### Scenario: Manager connects an integration

- **WHEN** a manager POSTs an integration for an in-scope company with a valid
  `erp_type` and credentials
- **THEN** an `ErpIntegration` is created, its credentials are persisted encrypted,
  and the response omits the secret values

#### Scenario: Non-manager is forbidden

- **WHEN** a member or viewer attempts to create an integration
- **THEN** the API responds 403 Forbidden and nothing is persisted

#### Scenario: Unknown erp_type is rejected

- **WHEN** the request uses an `erp_type` that is not a registered connector
- **THEN** the API responds 4xx and no integration is created

### Requirement: List and fetch ERP integrations within tenant scope

The API SHALL expose `GET /api/v1/erp-integrations` and `GET /api/v1/erp-integrations/{id}` returning integrations scoped to the caller's companies, and SHALL never include credential secrets.

- The list SHALL be restricted to the caller's in-scope companies; system admins
  MAY read across organizations.
- The list SHALL support an optional `company_id` filter and an
  `include_disconnected` flag (default: exclude soft-disconnected).
- Fetching an integration outside the caller's scope SHALL return 404.
- No response SHALL contain decrypted credential values.

#### Scenario: Scoped list excludes other tenants

- **WHEN** a member lists integrations
- **THEN** only integrations for their organization's companies are returned, with
  no credential secrets

#### Scenario: Out-of-scope integration returns 404

- **WHEN** a caller fetches an integration id belonging to another tenant
- **THEN** the API responds 404 Not Found

### Requirement: Update an ERP integration

The API SHALL expose `PATCH /api/v1/erp-integrations/{id}` for a manager to update the label and/or replace the credentials, keeping credentials encrypted.

- Only management roles MAY update; the integration MUST be in scope (else 404).
- Updated credentials SHALL be re-encrypted; omitted credentials SHALL leave the
  stored secret unchanged.
- The response SHALL NOT include credential secrets.

#### Scenario: Manager updates the label without touching credentials

- **WHEN** a manager PATCHes only the `label`
- **THEN** the label changes and the stored credentials remain intact and encrypted

### Requirement: Soft-disconnect and reconnect an integration

The API SHALL disconnect an integration by setting `disconnected_at` (retaining its accounts, entries, and sync history) rather than hard-deleting, and SHALL allow reconnecting.

- `POST /api/v1/erp-integrations/{id}/disconnect` SHALL set `disconnected_at` and
  require management authorization.
- `POST /api/v1/erp-integrations/{id}/reconnect` SHALL clear `disconnected_at`.
- Disconnecting SHALL NOT delete `ErpAccount`, `ErpEntry`, or `SyncState` rows.

#### Scenario: Disconnect retains data

- **WHEN** a manager disconnects an integration
- **THEN** `disconnected_at` is set and its accounts and entries still exist

#### Scenario: Reconnect clears the flag

- **WHEN** a manager reconnects a disconnected integration
- **THEN** `disconnected_at` becomes null and the integration is active again

### Requirement: Test an integration's connection

The API SHALL expose `POST /api/v1/erp-integrations/{id}/test-connection` that verifies reachability using the integration's connector and decrypted credentials, without importing the sync runner.

- The endpoint SHALL build the connector for the integration's `erp_type` from the
  decrypted credentials and report success/failure (e.g. `{ "ok": true|false }`).
- A connection failure SHALL be reported as a normal result (not a 500), so the
  client can display it.
- The endpoint SHALL require management authorization and an in-scope integration.

#### Scenario: Reachable ERP reports ok

- **WHEN** a manager tests a correctly-configured integration
- **THEN** the response indicates the connection succeeded

#### Scenario: Unreachable ERP reports failure, not a crash

- **WHEN** the ERP is unreachable or credentials are invalid
- **THEN** the response indicates failure with a message and HTTP 200

### Requirement: Refresh the account chart from the ERP

The API SHALL expose `POST /api/v1/erp-integrations/{id}/refresh-accounts` that re-fetches the ERP chart of accounts and upserts `ErpAccount` rows, preserving each account's `sync_enabled` selection.

- New accounts SHALL be inserted; existing accounts SHALL have their metadata
  (name, type, parent, `with_vat`) refreshed.
- An existing account's `sync_enabled` value SHALL be preserved (never reset by a
  refresh).
- The response SHALL report how many accounts were seen / added.
- The endpoint SHALL require management authorization and an in-scope integration,
  and SHALL run entirely within `web_api` (no `ai_api` import).

#### Scenario: New ERP accounts are added, selections preserved

- **WHEN** the ERP has gained accounts and an existing account was disabled, then a
  manager refreshes accounts
- **THEN** the new accounts are inserted and the previously disabled account
  remains `sync_enabled = false`

### Requirement: List and toggle ERP accounts

The API SHALL expose `GET /api/v1/erp-integrations/{id}/accounts` and `PATCH /api/v1/erp-accounts/{account_id}` so managers can review the native chart and select which accounts to sync.

- The account list SHALL be scoped through the integration's company; out-of-scope
  access SHALL return 404.
- `PATCH` SHALL allow setting `sync_enabled` and/or `with_vat`; it SHALL require
  management authorization.
- No manual create or delete of `ErpAccount` rows is provided (accounts are
  ERP-sourced).

#### Scenario: Manager disables an account for sync

- **WHEN** a manager PATCHes an account with `sync_enabled = false`
- **THEN** the account is persisted disabled and subsequent syncs skip its entries

#### Scenario: Account listing is tenant-scoped

- **WHEN** a caller lists accounts for an integration outside their scope
- **THEN** the API responds 404 Not Found
