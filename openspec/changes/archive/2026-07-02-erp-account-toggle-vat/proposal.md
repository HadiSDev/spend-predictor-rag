## Why

A real ERP holds far more accounts and postings than we want to analyze. We need
to **select which native ERP accounts to pull entries for** — pulling the whole
ledger every sync is wasteful and noisy. Separately, each ERP account is
configured **with or without VAT**, which we must record now so the categorizer
can later reconcile a predicted invoice total against the posted entry value (it
decides whether to sum invoice lines including or excluding VAT).

`ErpAccount` already carries `is_active` (the ERP's own active/inactive state) and
is scoped to a Company's `ErpIntegration`. What it lacks is an **our-side sync
selection toggle** and a **VAT characteristic**.

## What Changes

- `ErpAccount` gains a **`sync_enabled`** flag (our selection, not the ERP's) —
  when off, the sync does **not** fetch or persist entries for that account. It is
  distinct from `is_active`, which continues to mirror the ERP.
- `ErpAccount` gains a **`with_vat`** flag read from the ERP account (with-VAT vs
  without-VAT). Metadata only in this change — no amount computation yet.
- The on/off gate is enforced **at fetch time**: the sync runner reads the enabled
  account codes for the integration and passes them to `fetch_entries`, so we pull
  only the selected accounts instead of the entire ledger.
- The connector `fetch_entries` gains an **account-code filter**; `ErpAccountData`
  gains `with_vat`.
- The mock ERP exposes **`withVat`** on accounts and lets `GET /api/v1/entries`
  **filter by account codes**, so the fetch-time gate and VAT metadata run
  end-to-end deterministically.

## Capabilities

### New Capabilities
<!-- None. This reshapes existing capabilities; no new spec is introduced. -->

### Modified Capabilities
- `domain-model`: `ErpAccount` gains `sync_enabled` (our sync selection) and
  `with_vat` (ERP VAT characteristic); the account/entry ingestion rules are
  updated so disabled accounts yield no entries.
- `erp-connector-interface`: `fetch_entries` gains an account-code filter;
  `ErpAccountData` gains `with_vat`.
- `mock-erp-api`: accounts expose `withVat`; `GET /api/v1/entries` supports an
  `accounts` filter.

## Impact

- **Domain / ORM** (`web_api/db/models/erp_account.py`): `+sync_enabled`,
  `+with_vat`; a new additive Alembic migration.
- **Connector** (`web_api/connectors/`): `base.py` (`ErpAccountData.with_vat`,
  `fetch_entries(..., account_codes)`); `mock.py` implementation.
- **Sync runner** (`ai_api/sync/runner.py`): persist `with_vat`, preserve
  `sync_enabled` across syncs, read enabled codes, pass them to `fetch_entries`,
  and report skipped/selected counts.
- **Mock ERP** (`mock_erp/`): `withVat` on accounts; `accounts` filter on the
  entries endpoint; `models.py` schemas.
- **Tests**: sync-runner (disabled account ⇒ no entries), connector + mock-erp.
- **Out of scope**: a customer-facing API/UI to toggle `sync_enabled`, and any
  VAT-based amount math (both deferred to later changes). The categorizer,
  aggregation, redundancy, and recommender are unaffected.
