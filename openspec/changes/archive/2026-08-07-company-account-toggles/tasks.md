## 1. `with_vat` becomes a customer setting

Both upsert sites must change together. Fixing one leaves the toggle working
until the other runs, then reverting — which reads as "my setting randomly
resets", the hardest kind of bug to report.

- [x] 1.1 In `web_api/routers/erp_integrations.py:refresh_accounts`, set `with_vat` only when inserting a new `ErpAccount`; drop it from the fields an existing row has refreshed
- [x] 1.2 In `ai_api/sync/runner.py:_persist_accounts`, make the same split — seed on insert, preserve on update
- [x] 1.3 Leave `is_active`, `erp_account_name`, `erp_account_type`, `parent_code` and `raw_json` refreshed as they are; those are the ERP's
- [x] 1.4 Test (`tests/web_api/test_erp_integrations.py`): a manager sets `with_vat` opposite to the ERP, refreshes, and keeps their value while name and type update
- [x] 1.5 Test (`tests/test_sync_runner.py`): the same value survives a re-sync — the second writer, asserted separately
- [x] 1.6 Test: a newly discovered account still takes the ERP's reported `with_vat`

## 2. Frontend data layer

- [x] 2.1 Add `ErpAccountRead` and `ErpAccountUpdate` to `frontend/src/lib/types.ts`
- [x] 2.2 Add `frontend/src/lib/accounts.ts`: `accountsQueryOptions(api, integrationId)`, `updateAccountMutation`, `refreshAccountsMutation`, invalidating the account list on success
- [x] 2.3 Tests: the list request targets the integration, a toggle patches only the account it belongs to, and refresh posts to the integration

## 3. Route and navigation

- [x] 3.1 Add `routes/_authed/settings/companies.$companyId.accounts.tsx` with `staticData: { title: 'Accounts' }`, resolving the company's integration from the existing integrations query
- [x] 3.2 Add a "Manage accounts" item to the company row's action menu in `companies-panel.tsx`, disabled when the company has no connected integration — as an `onManageAccounts` callback rather than a `Link`, since the panel is presentational and rendered without a RouterProvider in its tests
- [x] 3.3 Regenerate `routeTree.gen.ts`
- [x] 3.4 Tests: the menu item links to the right company; it is disabled for a company with no integration

## 4. Accounts panel

- [x] 4.1 Add `components/settings/accounts-panel.tsx` (presentational, props-driven like `companies-panel.tsx`) listing code, name, type, and the Sync and VAT switches
- [x] 4.2 Each switch patches on change, on its own; on failure revert the switch and show the error against that account
- [x] 4.3 Add the search box over code and name, plus a header line stating total and sync-enabled counts
- [x] 4.4 Add bulk enable/disable acting on the **currently shown** accounts only, labelled with the count they will affect
- [x] 4.5 Add the refresh action, reporting `{seen, added}` from the response
- [x] 4.6 Add the empty state for an integration with no accounts yet, offering the refresh
- [x] 4.7 State what each toggle does: Sync off stops future ingestion and keeps existing entries; VAT records an assumption for reconciliation and recomputes nothing
- [x] 4.8 Disable every write control for a non-manager, with the reason stated (`canManageCompanies`)
- [x] 4.9 Tests: accounts render with both settings; one toggle patches one account; a failed toggle reverts and shows the error; search narrows the list; a bulk action touches only the filtered rows and announces the count; refresh reports seen/added; the empty state offers a refresh; a viewer sees everything disabled

## 5. Wrap-up

- [x] 5.1 Run `uv run pytest` — all backend tests pass
- [x] 5.2 Run the frontend suite and `tsc --noEmit` — tests pass and types are clean
- [x] 5.3 Update `CLAUDE.md`: `with_vat` is a customer setting seeded from the ERP and preserved by both `refresh-accounts` and the sync, not ERP metadata
- [x] 5.4 Check against the real database: toggle an account's VAT flag, run `uv run python -m ai_api.sync.runner`, and confirm the setting survived — the exact regression this change exists to prevent
