## Context

`run_sync` today is one long function that connects, bootstraps a tenant, then
runs seven stages. Only the bootstrap is wrong — everything from
`_begin_sync_state(session, integration_id)` down already operates on
`(company_id, integration_id)` and needs no change. `SyncState` is already keyed
per integration. The pipeline was built for many integrations; only its entry
point assumes one, and invents it.

Constraints:

- **`ai_api` may import `web_api`, never the reverse.** Reading `ErpIntegration`
  and `decrypt_config` is the permitted direction.
- **Credentials are encrypted at rest** (`WEB_API_CREDENTIAL_ENC_KEY`, Fernet)
  and the API never returns them. The runner is a trusted process on the same
  database, so it decrypts directly rather than going through the API.
- **A connector whose credential fields all have defaults writes no
  `ErpCredential` row** — established by `company-with-integration`. The runner
  must treat a missing credential row as "use the connector's defaults", not as
  an error.
- **Integrations are soft-disconnected** (`disconnected_at`), never deleted.

## Goals / Non-Goals

**Goals:**

- The set of things to sync is a database query, not an argument.
- A company created in Settings is synced by the next run, with no code or flag
  change.
- One broken ERP does not stop the others.
- Each integration advances its own watermark.

**Non-Goals:**

- Scheduling, retries, backoff, or a "sync now" API endpoint.
- Concurrency across integrations — sequential is fine at this scale and keeps
  failure attribution obvious.
- Any change to the per-integration pipeline: fetch order, categorization,
  invoice linking, and the downstream stubs stay exactly as they are.
- Multi-tenant safety review of the connectors themselves.

## Decisions

### The work list is `disconnected_at IS NULL`, and nothing else

Not "companies that are active", not "integrations with accounts". A connected
integration is precisely the statement "this company's ERP data should be read
from here" — it is what `POST /companies` and `POST /erp-integrations` create,
and what `disconnect` retracts.

Deliberately **not** filtered on `Company.is_active`. A deactivated company is
soft-deactivated for the customer-facing API; whether its ERP should stop being
polled is a separate product question, and silently coupling the two here would
be a decision made in the wrong place. If it should be coupled, that is its own
change with its own requirement.

### Credentials come from the row, with a missing row meaning "defaults"

```python
config = decrypt_config(credential.encrypted_config) if credential else {}
connector = get_connector(integration.erp_type, config)
```

The Debug ERP declares `base_url` and `api_key` with defaults and neither
required, so `{}` is a complete config for it. Treating a missing row as an
error would break exactly the integration the frontend creates by default.

A decryption failure (missing or rotated key) is a *per-integration* failure, not
a fatal one — it lands on that integration's `SyncState` and the run continues.
Otherwise one stale key stops every tenant.

### Failures are isolated per integration, and recorded where they happened

Today an exception marks `SyncState` as `error` and re-raises, killing the run.
With many integrations that means tenant #2 is punished for tenant #1's ERP
being down. Instead each integration is wrapped:

```python
for integration in work:
    try:
        results[integration.id] = _sync_one(...)
    except Exception as exc:
        _finish_sync_state(session, state, [], status="error", error=str(exc))
        results[integration.id] = {"status": "error", "error": str(exc)}
```

The process exit code is non-zero if **any** integration failed, so a scheduler
still sees the failure — but the other tenants got their data.

**Connection failure is one of these, not a precondition.** Today
`test_connection()` failing raises `RuntimeError` before any tenant work starts;
it moves inside the per-integration block.

### `since` resolves per integration, from its own watermark

Precedence: explicit `--since` (an operator backfill, applied to every
integration in the run) → that integration's `SyncState.last_invoice_date` →
`None` (full pull).

This is the change that makes `last_invoice_date` mean something: it is written
today and never read, so every run is a full re-fetch. It also removes the
incoherence of one global `--since` spanning integrations that are at different
points in their history.

Idempotency is unaffected either way — every persisted id is a `uuid5` of stable
parts, so a re-fetch upserts rather than duplicating. The watermark is an
efficiency measure, not a correctness one, which is why it is safe to adopt here.

### `--integration-id` filters; it never identifies

The distinction that makes it acceptable: it can only *narrow* the set the
database already produced. It cannot create a tenant, cannot name a company, and
an id that is not in the connected set is an error rather than a thing to
create. That is categorically different from `--company-name`, which decided
what existed.

### `run_synthetic` is removed rather than reworked

Its purpose was "populate a database from cold". After this change that is:
create a company with the Debug ERP in Settings, run the sync. Keeping a
function that means "run_sync, but only the mock ones" preserves the old mental
model — that synthetic data is a separate mode rather than an ordinary
integration — which is the thing being corrected.

### `run_sync` returns a dict keyed by integration id

One run covers several tenants, so a single flat summary can no longer describe
it. Each entry carries the previous summary shape plus `company_id`,
`erp_type`, and a `status` of `ok` or `error`. The CLI prints one block per
integration.

## Risks / Trade-offs

- **A cold database now syncs nothing, and that is the correct behaviour but a
  worse first-run experience.** → The CLI logs "no connected ERP integrations —
  create a company with an ERP connection in Settings first" rather than
  printing an empty summary that reads like a failure.
- **The runner needs the Fernet key it never needed before.** → Only when an
  integration actually stored credentials; the Debug ERP's all-default fields
  still need none. A missing key surfaces as that integration's error, naming
  the env var.
- **Sequential processing means total runtime is the sum of all integrations.**
  → Acceptable at current scale, and it keeps failure attribution and logging
  unambiguous. Concurrency is a later change if tenant count justifies it.
- **A long-running loop holds one `Session` across many integrations.** → Each
  integration commits as it goes (the existing persist helpers commit per stage),
  so a later failure cannot roll back an earlier tenant's data.
- **Losing `--reset` removes the "give me a clean slate" affordance.** →
  Deliberate: that flag deleted the integrations defining the work list. Wiping
  a dev database is `alembic downgrade base && alembic upgrade head`, or a
  targeted delete — a database operation, not a sync flag.
- **`--since` as a global override is still slightly incoherent** across
  integrations at different points. → Kept because a backfill genuinely wants
  "re-pull everything from date X", and it is explicit and rare rather than the
  default path.

## Migration Plan

No data migration; no schema change. The Demo Org tenant this replaces has
already been deleted (1 org, 1 company, 1 integration, 25 accounts, 649 entries,
175 invoices, 358 lines, 358 ground-truth and 358 audit rows). Vendors were kept
— `Vendor` is a global catalog, and `GET /vendors` only returns suppliers the
caller's own invoices reference, so they stay invisible until a real sync
re-references them.

Rollback is reverting the commit; nothing persisted depends on the new shape.

## Open Questions

- Should a deactivated `Company` stop its integration from being polled? Left
  uncoupled deliberately (see above) — worth deciding when company deactivation
  has a real workflow behind it.
- Where does a scheduler live once there is more than one tenant to sync — cron
  calling this CLI, or an API-triggered background job? Out of scope here, but
  the per-integration summary and the non-zero exit code are shaped to suit
  either.
