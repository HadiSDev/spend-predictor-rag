## Why

`ErpEntry` has two modeling rough edges that hurt clarity and correct reporting:
its single `entry_date` is ambiguously named (it is really the ledger posting
date), and it stores a redundant `erp_integration_id` even though every entry
already reaches its integration through its account
(`ErpEntry.erp_account_id → ErpAccount.erp_integration_id`) and its company via
`company_id`. Reporting is about to aggregate spend by period, so the date axis
needs an unambiguous name first.

## What Changes

- **Rename** `ErpEntry.entry_date` → `accounting_date` (the posting/accounting
  date), through the model, the `ErpEntryData` connector DTO, the mock ERP
  mapping, the sync runner, the `ErpEntryRead` schema, and ordering in the
  entries endpoint. **BREAKING** (wire field `entry_date` → `accounting_date`).
- **Remove** `ErpEntry.erp_integration_id` (column, FK, and the
  `ErpIntegration.erp_entries` back-reference). The integration is derived
  through the entry's account when needed.
  - The sync runner scopes an integration's entries by **joining through
    `ErpAccount`** (`ErpAccount.erp_integration_id == integration_id`) instead of
    the dropped column; the deterministic entry id keeps using the integration id
    at persist time, so idempotency is unchanged.
  - `ErpEntryRead` drops `erp_integration_id`. **BREAKING**.
- Alembic migration: rename the column and drop `erp_integration_id`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `domain-model`: `ErpEntry` records an `accounting_date` (the posting date), and
  an entry's integration is reached through its account rather than a direct
  `erp_integration_id` column.

## Impact

- `web_api/db/models/erp_entry.py` (rename + drop column/relationship),
  `web_api/db/models/erp_integration.py` (drop `erp_entries` back-ref),
  `web_api/connectors/base.py` + `connectors/mock.py` (DTO + mapping),
  `web_api/schemas.py` (`ErpEntryRead`), `web_api/routers/erp_entries.py`
  (ordering), `ai_api/sync/runner.py` (persist + integration-scoped query).
- One Alembic migration (rename column, drop column + FK).
- Tests: `tests/web_api/test_erp_entries.py`, `tests/test_sync_runner.py`.
- Docs: `CLAUDE.md` (ErpEntry description / entry field notes).
