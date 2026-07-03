## Context

`web_api/` owns the domain (ORM, DB, Clerk-auth API) and the ERP connectors;
`ai_api/` owns the AI/sync workflows and **imports** the domain from `web_api`.
The dependency is strictly one-way: **`web_api` must never import `ai_api`**.

Today integrations and accounts are created/updated only by the sync runner's
bootstrap and `_persist_accounts` (in `ai_api`). There is no API to connect an
ERP, manage credentials, or toggle the `sync_enabled`/`with_vat` selection that
`erp-account-toggle-vat` added. Management endpoints already exist for companies
(`require_management` gate, `get_managed_company` scope helper, Create/Update
Pydantic bodies, soft-deactivate). This change adds an ERP-integration controller
following those conventions, plus encrypted credential storage.

## Goals / Non-Goals

**Goals:**
- Integration CRUD (create with credentials, read, update, soft-disconnect/
  reconnect), tenant-scoped and management-gated.
- Encrypted-at-rest credential storage (`ErpCredential`), never returned.
- `test-connection` and `refresh-accounts` actions, implemented **inside**
  `web_api` via the connector registry.
- Account list + per-account toggle (`sync_enabled`, `with_vat`).

**Non-Goals:**
- No trigger-full-sync endpoint — that needs the `ai_api` runner, which `web_api`
  cannot import. (A future event/queue bridge is out of scope.)
- No manual create/delete of `ErpAccount` (ERP-sourced).
- No credential-key rotation tooling or secrets-manager integration (env key only).
- No hard-delete of integrations.

## Decisions

### D1 — Credentials in a separate `ErpCredential` table, Fernet-encrypted
New `ErpCredential(id, erp_integration_id FK, encrypted_config, created_at,
updated_at)`. `encrypted_config` is a Fernet token over the JSON config
(`{base_url, api_key, ...}`). A `web_api/credentials.py` helper wraps
encrypt/decrypt using a key from `config.WEB_API_CREDENTIAL_ENC_KEY`.
- *Why separate table:* the domain model already states credentials are "stored
  separately, encrypted, not in this [integration] table." Keeps secrets off the
  frequently-read integration row and out of its response model.
- *Why Fernet:* `cryptography` is already available (transitive dep); Fernet is
  authenticated symmetric encryption with a simple API.
- *Key handling:* the key comes from env. If unset, credential **write** endpoints
  fail fast with a clear 500/misconfig error (never store plaintext). Documented in
  `.env.example`. Rotation is out of scope.
- *Alternative rejected:* an `encrypted_config` column on `ErpIntegration` — simpler
  but re-couples secrets to the hot read path and the model explicitly wants them
  separate.

### D2 — Reads for members, writes for managers; credentials never serialized
Reads (`GET` list/detail, account list) use `tenant_scope` (any org member).
Writes (create/update/disconnect/reconnect/test/refresh, account PATCH) use
`require_management`. `ErpIntegrationRead` exposes only non-secret fields plus a
`has_credentials: bool`; there is no field that carries decrypted secrets.
- *Why:* mirrors the companies controller; least-privilege for secrets.

### D3 — `get_managed_integration` scope helper
Add a dep mirroring `get_managed_company`: fetch the `ErpIntegration`, 404 if
missing or its `company_id` is not in `scope.company_ids` (or not managed).
Account endpoints resolve scope through the parent integration's company.
- *Why:* one consistent tenant-isolation choke point; 404 (not 403) on out-of-scope
  so existence isn't leaked.

### D4 — `refresh-accounts` upsert lives in `web_api` (no `ai_api` reuse)
The runner's `_persist_accounts` (in `ai_api`) already upserts accounts preserving
`sync_enabled`, but `web_api` cannot import it. Implement the same small upsert in
`web_api` (a `services`/router helper): `connector.fetch_accounts()` → for each,
upsert by `(integration_id, erp_account_code)`, refresh metadata + `with_vat`, set
`sync_enabled` **only when creating**. Deterministic id via the same scheme is not
required here (web_api can use its own id/default_factory) — matching is by
`(erp_integration_id, erp_account_code)`.
- *Trade-off:* a small duplication of upsert logic across the boundary. Accepted —
  the alternative (importing `ai_api`) violates the architecture. If it drifts, a
  shared helper can move **into** `web_api` and `ai_api` can import it (allowed
  direction).

### D5 — `test-connection` reports failure as data, not an error
Build the connector from decrypted credentials, call `authorize()` +
`test_connection()`, and return `{ok, message}`. Connection/auth exceptions are
caught and returned with `ok=false` and HTTP 200, so the UI can render the result.
- *Why:* a failed ERP probe is an expected outcome, not a server error.

### D6 — `erp_type` validated against the connector registry
Add `available_connectors() -> list[str]` to `web_api/connectors/__init__.py`.
Create/refresh/test resolve via `get_connector(erp_type, config)`; an unknown type
returns 4xx before persisting.

## Risks / Trade-offs

- **Secret-at-rest key management** → env-provided Fernet key; write endpoints fail
  closed if the key is missing (never store plaintext). Rotation/secrets-manager
  deferred and documented as a risk.
- **Credential leakage via responses** → no schema field carries secrets; a test
  asserts responses never contain the plaintext api_key.
- **Upsert duplication across the `web_api`/`ai_api` boundary** (D4) → accepted to
  preserve the one-way dependency; note it and keep the helper in `web_api`.
- **Live connector calls in request handlers** (test/refresh) → wrap in try/except
  with a timeout the connector already enforces (httpx 30s); report failures
  gracefully; these are manager-triggered, low-frequency actions.
- **Disconnect vs. sync** → a soft-disconnected integration should be skipped by
  future syncs; that runner-side behavior is out of scope here (this change only
  sets the flag and retains data).

## Migration Plan

1. Add `db/models/erp_credential.py` (+ relationship on `ErpIntegration`); generate
   an additive Alembic migration for the `erp_credentials` table (revision id
   ≤ 32 chars). Run `alembic upgrade head` (`DATABASE_URL=…@localhost:5433/…`).
2. Add `WEB_API_CREDENTIAL_ENC_KEY` to `config.py` + `.env.example`; add
   `credentials.py` (Fernet helper) and `available_connectors()`.
3. Add schemas, `get_managed_integration`, the router, and register it in `app.py`.
4. Tests (fake connector) + `uv run pytest`.
- **Rollback:** drop the `erp_credentials` table and revert code; additive, so no
  data loss for existing tables.

## Open Questions

- Should a soft-disconnected integration be auto-skipped by the sync runner? Left to
  a follow-up (runner-side), since it crosses into `ai_api`.
- Bulk account toggle (`PATCH /erp-integrations/{id}/accounts` with a list) — single
  PATCH ships now; bulk can be added if the dashboard needs it.
- Multiple historical credentials per integration (rotation history) — modeled as
  one active credential for now.
