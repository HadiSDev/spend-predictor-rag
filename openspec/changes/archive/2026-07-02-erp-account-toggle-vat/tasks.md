## 1. Domain model & migration

- [x] 1.1 Add `sync_enabled` (bool, default `True`) and `with_vat` (bool, default `False`) to `ErpAccount` in `src/web_api/db/models/erp_account.py`
- [x] 1.2 Generate an additive Alembic migration for `erp_accounts.sync_enabled` + `erp_accounts.with_vat` (revision id ≤ 32 chars); run `uv run alembic upgrade head` against Postgres (`DATABASE_URL=…@localhost:5433/…`)
- [x] 1.3 Confirm `SQLModel.metadata.create_all` (runner reset path) produces the new columns

## 2. Connector interface & DTOs

- [x] 2.1 Add `with_vat: bool = False` to `ErpAccountData` in `src/web_api/connectors/base.py`
- [x] 2.2 Change the abstract `fetch_entries` signature to `fetch_entries(since: date | None = None, account_codes: set[str] | None = None) -> list[ErpEntryData]` (None = all; empty set = none)

## 3. Mock ERP: VAT flag + entries account filter

- [x] 3.1 Add a `withVat` field to the mock chart of accounts (`mock_erp/data/accounts.py`), covering both with-VAT and without-VAT accounts
- [x] 3.2 Expose `withVat` in the accounts endpoint payload (`mock_erp/main.py` account dicts) and add it to `AccountResponse` in `mock_erp/models.py`
- [x] 3.3 Add an `accounts` query param (comma-separated codes) to `GET /api/v1/entries` in `mock_erp/main.py`, filtering entries by `account.accountNumber`; compose with `since` + pagination

## 4. Mock connector implementation

- [x] 4.1 Map `with_vat` from the account payload in `MockErpConnector.fetch_accounts`
- [x] 4.2 Implement the `account_codes` filter in `MockErpConnector.fetch_entries` (serialize to the `accounts` query param; `None` ⇒ omit; empty set ⇒ return `[]` without hitting the ERP or by passing an empty filter)

## 5. Sync runner: fetch-time gate + persist VAT

- [x] 5.1 In `_persist_accounts`, set `sync_enabled` only when creating a new `ErpAccount` row (preserve existing selection); always refresh `with_vat` from the DTO
- [x] 5.2 After persisting accounts, read the enabled account codes for the integration (`sync_enabled == True`) from the DB
- [x] 5.3 Pass the enabled codes to `connector.fetch_entries(since=…, account_codes=enabled_codes)` in `run_sync`
- [x] 5.4 Add selected/skipped account counts to the summary + logging (e.g. accounts total, enabled, entries fetched)

## 6. Tests & verification

- [x] 6.1 Sync-runner test: disabling an `ErpAccount` (`sync_enabled=False`) results in zero `ErpEntry` rows for that account after a sync
- [x] 6.2 Sync-runner test: `sync_enabled` survives a re-sync (toggle off, re-sync, still off) while `with_vat`/name refresh
- [x] 6.3 Connector test: `fetch_entries(account_codes={"6010"})` returns only 6010 entries; `account_codes=set()` returns none
- [x] 6.4 Mock ERP test: `GET /api/v1/entries?accounts=…` filters correctly and composes with pagination; accounts payload includes `withVat`
- [x] 6.5 Assert persisted `ErpAccount.with_vat` reflects the ERP payload (both true and false cases)
- [x] 6.6 Run `uv run pytest` and an end-to-end sync against the mock; confirm entries are limited to enabled accounts
