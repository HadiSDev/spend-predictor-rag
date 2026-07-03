## Context

`ErpAccount` is the ERP's native chart-of-accounts node (e.g. `6010 = Cloud
Hosting`), scoped to a Company's `ErpIntegration`; every `ErpEntry` maps to one
`ErpAccount`. It already has `is_active` (mirrors the ERP's active flag) and
`erp_account_type`. The sync runner (post entry-first rewire) fetches accounts,
persists them, fetches **all** entries, and links them to invoice scans by
voucher.

Two gaps: (1) real ERPs expose far more accounts/entries than we want to analyze,
so we need to **select** which accounts to pull entries for and pull only those;
(2) each ERP account is configured with or without VAT, which we must record now
for a later categorization step (reconciling a predicted invoice total against the
posted entry value depends on whether lines are summed inclusive or exclusive of
VAT).

## Goals / Non-Goals

**Goals:**
- Add `ErpAccount.sync_enabled` (our selection) and `ErpAccount.with_vat` (ERP
  characteristic).
- Enforce the on/off gate **at fetch time**: pull entries only for enabled
  accounts, not the whole ledger.
- Read `with_vat` from the ERP account and store it (metadata only).
- Exercise both end-to-end through the mock ERP.

**Non-Goals:**
- No customer-facing API/UI to toggle `sync_enabled` (later change). The field
  exists and is respected; how a user flips it is out of scope here.
- No VAT-based amount math — `with_vat` is stored, not consumed, in this change.
- No change to categorization, aggregation, redundancy, or the recommender.
- `is_active` semantics are unchanged.

## Decisions

### D1 — `sync_enabled` is ours; `is_active` stays the ERP's
Two separate booleans on `ErpAccount`: `is_active` (ERP active flag, refreshed
from the ERP each sync) and `sync_enabled` (our selection, **never** overwritten
by a fetch). `sync_enabled` defaults to `true`.
- *Why:* the ERP's notion of "active" and our notion of "pull this account" are
  different concerns. An account can be active in the ERP yet deselected by us
  (noise), or inactive yet historically interesting.
- *Alternative rejected:* reuse `is_active` as the gate. It would couple our
  selection to the ERP's state and get clobbered on every refresh.

### D2 — Gate at fetch time via an account-code filter
The runner reads the enabled account codes for the integration from the DB and
passes them to `fetch_entries(since, account_codes)`. The connector (and mock)
filter server-side so unselected accounts are never transferred.
- *Why:* the user's constraint is "there can be a lot of ERP data — only fetch the
  accounts we selected." Filtering at persist time would still transfer everything.
- *Ordering:* accounts are fetched and persisted **before** entries (already the
  case), so the enabled set is known before the entry fetch. On the very first
  sync, accounts are persisted with `sync_enabled = true` by default, so the set
  is non-empty and entries flow.
- *Empty set:* an explicit empty enabled set fetches **no** entries (correct — the
  user selected nothing). `None` means unfiltered (back-compat / callers that
  don't gate).

### D3 — Preserve `sync_enabled` on upsert
`_persist_accounts` refreshes name/type/parent/`is_active`/`with_vat`/`raw` on
every sync but sets `sync_enabled` **only when creating** a new row; existing rows
keep their value.
- *Why:* a re-sync must not silently re-enable accounts a user turned off.

### D4 — `with_vat` read from the ERP account, defaulting false
`ErpAccountData` gains `with_vat: bool = False`; `fetch_accounts` maps it from the
payload; `_persist_accounts` writes it. Mock accounts expose `withVat`.
- *Why:* keeps the flag authoritative from the source. Default `false` when the
  ERP omits it is safe (no VAT assumed) and non-breaking.

### D5 — Mock entries endpoint gains an `accounts` filter
`GET /api/v1/entries?accounts=6010,6020` returns only entries whose
`account.accountNumber` is in the set; omitted ⇒ all. Composes with `since` and
pagination. The connector serializes the enabled codes into this param.
- *Why:* mirrors the real fetch-time gate deterministically. Filtering in the mock
  (not the connector) proves data is not transferred for unselected accounts.

## Risks / Trade-offs

- **First sync still pulls everything** (all accounts default enabled) → acceptable
  and backward-compatible; selection is an opt-out. Tests prove that disabling an
  account excludes its entries.
- **Default-true means no fetch reduction until a user selects** → the mechanism is
  delivered here; the actual narrowing happens once accounts are toggled (via a
  future endpoint). Documented as a non-goal, not a regression.
- **Voucher completeness when accounts are disabled** → if some accounts of a
  voucher are disabled, that voucher's entry set becomes partial. That is the
  intended semantics ("we only get entries for accounts turned on"); invoice-scan
  linking is unaffected (linking is by voucher, and scans are fetched separately).
- **`account_codes` as a query param length** → many codes could make a long URL.
  Fine for the mock; a real connector can POST a filter or page. Interface takes a
  set, leaving room for that.
- **Migration** (two nullable/defaulted booleans on `erp_accounts`) → additive and
  backfill-safe; existing rows default `sync_enabled = true`, `with_vat = false`.

## Migration Plan

1. Add `ErpAccount.sync_enabled` (bool, default true) and `with_vat` (bool,
   default false). Generate one additive Alembic migration (revision id ≤ 32 chars
   to fit `alembic_version.version_num`).
2. `uv run alembic upgrade head` (point `DATABASE_URL` at the running Postgres,
   host port 5433 in this environment).
3. Land connector + mock changes together (mock is the only implementation).
4. Update the runner to read enabled codes and pass them to `fetch_entries`; run
   the pipeline against the mock to confirm disabled accounts yield no entries.
- **Rollback:** revert the migration (drop the two columns) and the code; additive
  and nullable/defaulted, so no data loss.

## Open Questions

- Real-ERP field name/representation for the VAT characteristic (per ERP) — the
  DTO normalizes it; deferred to the first real connector.
- The default policy for `sync_enabled` on real, large charts (all-on vs
  all-off-then-opt-in) — kept all-on here for back-compat; a future onboarding flow
  can seed the selection.
- Whether a bulk toggle endpoint belongs in `web-api-company-management` or a new
  capability — deferred with the API/UI work.
