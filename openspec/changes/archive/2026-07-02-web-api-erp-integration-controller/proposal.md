## Why

Customers must be able to connect their own ERP from the platform and manage what
gets pulled — but the web API has **no endpoints for ERP integrations or their
accounts**. Integrations are created only by the sync runner's bootstrap, native
accounts are read-only, and the `sync_enabled`/`with_vat` selection added by
`erp-account-toggle-vat` has no customer-facing surface. We need an ERP
integration controller: create/connect an integration (with credentials), manage
its accounts (read, toggle selection, refresh the chart from the ERP), verify the
connection, and disconnect — all within `web_api` (which must never import
`ai_api`).

## What Changes

- **New ERP-integration management endpoints** under `/api/v1` (management-gated
  writes; reads for any org member; **credentials never returned**):
  - `GET /erp-integrations` (scoped list, `?company_id`, `?include_disconnected`),
    `GET /erp-integrations/{id}`.
  - `POST /erp-integrations` — create/connect: `company_id`, `erp_type` (validated
    against the connector registry), `label`, and **credentials** (e.g. `base_url`,
    `api_key`) stored **encrypted at rest**.
  - `PATCH /erp-integrations/{id}` — update label and/or credentials.
  - `POST /erp-integrations/{id}/disconnect` — **soft-disconnect** (sets
    `disconnected_at`; retains accounts/entries/history); `…/reconnect` clears it.
  - `POST /erp-integrations/{id}/test-connection` — authorize + reachability check
    via the connector (uses decrypted credentials).
  - `POST /erp-integrations/{id}/refresh-accounts` — re-fetch the chart of accounts
    from the ERP and upsert `ErpAccount` rows (adds new, refreshes existing),
    **preserving each account's `sync_enabled` selection**.
- **ERP-account endpoints**: `GET /erp-integrations/{id}/accounts` (list, per
  integration) and `PATCH /erp-accounts/{account_id}` (set `sync_enabled` and/or
  `with_vat`). No manual create/delete — accounts are ERP-sourced.
- **Credential storage**: a new **`ErpCredential`** entity holding the integration's
  connection config **encrypted** (Fernet, key from env); decrypted only
  server-side to build a connector; never serialized to clients.

## Capabilities

### New Capabilities
- `web-api-erp-integration-management`: integration CRUD (create with credentials,
  read, update, soft-disconnect/reconnect), connection test, account chart refresh,
  and per-account selection toggling — tenant-scoped and management-gated.

### Modified Capabilities
- `domain-model`: add the `ErpCredential` entity (encrypted connection config,
  1:1 with `ErpIntegration`); document the integration soft-disconnect lifecycle.

## Impact

- **Web API** (`src/web_api/`): new `routers/erp_integrations.py`; new
  `credentials.py` (Fernet encrypt/decrypt helper) reading a key from `config.py`;
  a `get_managed_integration` dep + `available_connectors()` accessor on the
  connector registry; `ErpIntegration`/`ErpAccount`/credential schemas in
  `schemas.py`; router registration in `app.py`; the account-refresh upsert
  implemented in `web_api` (cannot reuse `ai_api` runner logic).
- **Domain / ORM**: new `db/models/erp_credential.py`; a new Alembic migration
  (revision id ≤ 32 chars).
- **Config / env**: `WEB_API_CREDENTIAL_ENC_KEY` (Fernet key); documented in
  `.env.example` and `CLAUDE.md`.
- **Tests**: integration CRUD + tenant isolation + management gating; credentials
  never leak in responses; disconnect/reconnect; test-connection and
  refresh-accounts against a fake/mock connector; account toggle.
- **Not touched**: `ai_api` (sync runner, categorizer) — no import, no trigger-sync
  endpoint (that boundary is enforced). Full pipeline sync remains a runner concern.
