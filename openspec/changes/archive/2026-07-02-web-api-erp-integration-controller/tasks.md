## 1. Credential storage (model + encryption + config)

- [x] 1.1 Add `src/web_api/db/models/erp_credential.py`: `ErpCredential(id, erp_integration_id FK → erp_integrations, encrypted_config text, created_at, updated_at)`; register in `db/models/__init__.py`; add `credential` relationship on `ErpIntegration`
- [x] 1.2 Add `WEB_API_CREDENTIAL_ENC_KEY` to `src/web_api/config.py` (+ document in `.env.example`)
- [x] 1.3 Add `src/web_api/credentials.py`: Fernet `encrypt_config(dict) -> str` / `decrypt_config(str) -> dict` using the env key; raise a clear misconfig error when the key is unset (never store plaintext)
- [x] 1.4 Generate an additive Alembic migration for `erp_credentials` (revision id ≤ 32 chars); run `uv run alembic upgrade head` (`DATABASE_URL=…@localhost:5433/…`); confirm `create_all` builds the table

## 2. Connector registry + scope dep

- [x] 2.1 Add `available_connectors() -> list[str]` to `src/web_api/connectors/__init__.py`
- [x] 2.2 Add `get_managed_integration(session, scope, integration_id) -> ErpIntegration` in `deps.py` (404 if missing/out-of-scope; management-gated where used), mirroring `get_managed_company`

## 3. Schemas

- [x] 3.1 In `schemas.py`: `ErpIntegrationRead` (non-secret fields + `has_credentials: bool`, `connected_at`, `disconnected_at`), `ErpIntegrationCreate` (company_id, erp_type, label?, credentials dict), `ErpIntegrationUpdate` (label?, credentials?)
- [x] 3.2 `ErpAccountRead` (code, name, type, parent_code, is_active, sync_enabled, with_vat) and `ErpAccountUpdate` (sync_enabled?, with_vat?)
- [x] 3.3 `ConnectionTestResult` (`ok: bool`, `message: str | None`) and `RefreshAccountsResult` (`seen: int`, `added: int`)

## 4. Router: integration CRUD + actions

- [x] 4.1 Create `src/web_api/routers/erp_integrations.py` (`prefix="/api/v1"`, `tags=["erp-integrations"]`)
- [x] 4.2 `GET /erp-integrations` (scope, `?company_id`, `?include_disconnected`) and `GET /erp-integrations/{id}` — never serialize secrets
- [x] 4.3 `POST /erp-integrations` (require_management): validate `company_id` in scope + `erp_type` in `available_connectors()`; create integration + encrypted `ErpCredential`; 4xx on unknown erp_type
- [x] 4.4 `PATCH /erp-integrations/{id}` (require_management): update label; re-encrypt credentials if provided, else leave unchanged
- [x] 4.5 `POST /erp-integrations/{id}/disconnect` and `…/reconnect` (require_management): set/clear `disconnected_at`; retain related rows
- [x] 4.6 `POST /erp-integrations/{id}/test-connection` (require_management): build connector from decrypted creds, `authorize()` + `test_connection()`, return `ConnectionTestResult` (failures → `ok=false`, HTTP 200)
- [x] 4.7 `POST /erp-integrations/{id}/refresh-accounts` (require_management): `connector.fetch_accounts()` → upsert `ErpAccount` by `(integration_id, code)`, refresh metadata + `with_vat`, set `sync_enabled` only on create; return `RefreshAccountsResult`

## 5. Router: account read + toggle

- [x] 5.1 `GET /erp-integrations/{id}/accounts` (scope via integration): list `ErpAccountRead`
- [x] 5.2 `PATCH /erp-accounts/{account_id}` (require_management, scope via parent integration): set `sync_enabled` and/or `with_vat`; 404 out-of-scope

## 6. Wire up + docs

- [x] 6.1 Register the router in `src/web_api/app.py`
- [x] 6.2 Update `CLAUDE.md` endpoints list + note `WEB_API_CREDENTIAL_ENC_KEY`

## 7. Tests & verification

- [x] 7.1 Create: manager creates integration for in-scope company; credentials stored encrypted; response has no secret; unknown `erp_type` → 4xx; non-manager → 403; out-of-scope company → 404
- [x] 7.2 Read: list scoped (no cross-tenant), `include_disconnected` behavior, detail 404 out-of-scope; **no response ever contains the plaintext api_key**
- [x] 7.3 Update: label-only leaves credentials intact; credentials replace re-encrypts
- [x] 7.4 Disconnect sets `disconnected_at` and retains accounts/entries; reconnect clears it
- [x] 7.5 test-connection: ok=true for a reachable fake connector; ok=false (HTTP 200) when it raises
- [x] 7.6 refresh-accounts: new accounts added; a previously disabled account keeps `sync_enabled=false`; result counts correct
- [x] 7.7 accounts: list scoped; PATCH toggles `sync_enabled`/`with_vat`; out-of-scope 404; non-manager 403
- [x] 7.8 `uv run pytest` (web_api + full suite) green
