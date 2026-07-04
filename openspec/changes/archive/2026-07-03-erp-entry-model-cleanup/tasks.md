## 1. Model & schema

- [x] 1.1 Rename `ErpEntry.entry_date` → `accounting_date` in
  `web_api/db/models/erp_entry.py`
- [x] 1.2 Remove `ErpEntry.erp_integration_id` (column, FK) and the
  `erp_integration` relationship
- [x] 1.3 Remove the `erp_entries` back-reference from
  `web_api/db/models/erp_integration.py`
- [x] 1.4 `ErpEntryData` (`connectors/base.py`): rename `entry_date` →
  `accounting_date`; update `connectors/mock.py` mapping
- [x] 1.5 `ErpEntryRead` (`schemas.py`): rename `entry_date` → `accounting_date`,
  drop `erp_integration_id`

## 2. Sync runner

- [x] 2.1 `_persist_entries`: stop setting `erp_integration_id`; set
  `accounting_date` from `ErpEntryData.accounting_date` (keep the deterministic
  entry id derived from `integration_id`)
- [x] 2.2 `_categorize_pending`: scope the integration's entries by joining
  `ErpEntry → ErpAccount` and filtering `ErpAccount.erp_integration_id`
- [x] 2.3 Entries endpoint (`routers/erp_entries.py`): order by `accounting_date`

## 3. Migration

- [x] 3.1 Alembic: `alter_column` rename `entry_date` → `accounting_date`; drop
  `erp_integration_id` column + FK (downgrade re-adds nullable column + FK and
  renames back)

## 4. Tests & docs

- [x] 4.1 Update `tests/web_api/test_erp_entries.py` (seed/assert
  `accounting_date`; no `erp_integration_id` in the read model)
- [x] 4.2 Update `tests/test_sync_runner.py` (entry date field; entries scoped via
  account; assert `erp_integration_id`/`entry_date` absent from `ErpEntry`)
- [x] 4.3 `CLAUDE.md`: note `accounting_date` and that the entry's integration is
  via its account
- [x] 4.4 `uv run pytest` — full suite green
