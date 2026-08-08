## Why

The sync runner invents its own tenant instead of reading the one the product
already has. `_bootstrap_tenant` mints an Organization, Company and
`ErpIntegration` from hashed constants (`"Demo Org"` / `"Demo Company"`), takes
credentials from `argv`, and drops the whole schema by default.

This is not a cosmetic problem. The bootstrapped organization gets
`clerk_org_id = None`, so **no Clerk user can ever be scoped into it** — a real
run produced 649 entries, 175 invoices and 358 lines that the API and the new
Entries page correctly showed as nothing, because they belonged to an
organization nobody can belong to. At the same time a real company created
through Settings, with a connected Debug ERP integration and an encrypted
credential row, sat unsynced: the runner did not know it existed.

The database already records exactly which companies have a connected ERP and
what credentials each one uses. The runner should read that, not be told.

## What Changes

- **BREAKING** `run_sync()` takes no tenant or credential arguments. It
  discovers its work: every `ErpIntegration` with `disconnected_at IS NULL`.
  For each one it reads `erp_type` and `company_id` from the row, decrypts that
  integration's `ErpCredential` into the connector config, and runs the existing
  pipeline unchanged against it.
- **BREAKING** Remove `_bootstrap_tenant` and the flags that fed it —
  `--org-name`, `--company-name`, `--api-key`, `--base-url`. Companies and
  integrations are created through the frontend; the runner never creates a
  tenant.
- **BREAKING** Remove `--reset` (and its default of *true*). Dropping the schema
  now destroys the integration rows that define the work list, so the flag is
  not merely dangerous but self-defeating.
- **BREAKING** Remove `run_synthetic()`. With the mock ERP reached like any other
  connector, it is exactly `run_sync()` for a tenant whose only integration is
  the Debug ERP — a company created in Settings, as any other.
- **Per-integration failure isolation.** One unreachable ERP records an error on
  its own `SyncState` and the run continues to the next integration, instead of
  aborting every other tenant's sync.
- **Per-integration watermarks.** `SyncState.last_invoice_date` is written today
  but never read back. Each integration's next run now starts from its own
  watermark. A single global `--since` is meaningless once one run covers many
  integrations; it stays available only as an explicit override for a backfill.
- **Add `--integration-id` as a filter, not as identity.** It narrows the
  discovered work list to one integration for an operator re-running a single
  failed sync. It never names a company, and it cannot cause one to be created.
- **Summary keyed by integration**, since one run now covers several.

## Capabilities

### New Capabilities

- `sync-pipeline-orchestration`: how the sync runner discovers what to sync,
  where it gets credentials, how per-integration failures and watermarks are
  handled, and what it reports. The per-integration *ingest ordering* stays in
  `erp-connector-interface`, which this does not change.

### Modified Capabilities

*(none — no existing requirement changes. `erp-connector-interface`'s "Sync
runner ingests entries before invoice scans" describes ordering within one
integration and remains true verbatim.)*

## Impact

**Code** — `src/ai_api/sync/runner.py` only:

- `_bootstrap_tenant`, `run_synthetic` deleted; `main()` argument parser cut down
  to `--integration-id` and `--since`.
- The body from `_begin_sync_state` onward already threads
  `(company_id, integration_id)` through every step, so it extracts into a
  `_sync_one(session, integration, connector, since)` with no change to what it
  does — this is a change to where the ids come from, not to the pipeline.
- `ai_api` gains an import of `web_api.credentials.decrypt_config`, which is the
  permitted dependency direction.

**No schema change.** `ErpIntegration`, `ErpCredential` and `SyncState` already
carry everything needed; `SyncState.last_invoice_date` simply starts being read.

**Deployment** — the runner now needs `WEB_API_CREDENTIAL_ENC_KEY` whenever any
integration has stored credentials, because it decrypts them. An integration
whose connector fields all have defaults still needs no key.

**Docs** — `CLAUDE.md`'s sync-pipeline line. `openspec/specs/dashboard/spec.md`
contains illustrative `run_sync(company_id)` / `run_synthetic(company_id)`
snippets that go stale; that document is unbuilt-Streamlit prose with no
normative requirements (and is superseded by the React frontend), so it is left
alone rather than half-corrected.

**Operationally** — `python -m ai_api.sync.runner` is no longer a one-command
demo from a cold database. Creating the company and its ERP connection in
Settings is now a prerequisite, which is the intended flow.

## Not in Scope

- No change to what a sync *does* per integration: fetch order, categorization,
  linking, and the downstream stubs are untouched.
- No scheduling, no concurrency across integrations, no API-triggered sync.
  Integrations are processed sequentially; a "sync now" endpoint is a separate
  change.
