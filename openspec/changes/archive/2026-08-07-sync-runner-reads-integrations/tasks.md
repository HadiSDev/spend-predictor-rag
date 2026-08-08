## 1. Test harness for the runner

The runner has no tests today (`tests/` has only `web_api/` and `synthdata/`),
so the harness comes first — otherwise the rest is a rewrite with nothing
holding it in place.

- [x] 1.1 Add `tests/ai_api/__init__.py` and `tests/ai_api/conftest.py` with an in-memory SQLite engine monkeypatched onto `ai_api.sync.runner.engine`, following `tests/web_api/conftest.py`
- [x] 1.2 Add a `FakeConnector` registered under a test `erp_type`, returning a fixed handful of accounts, vendors, entries and one invoice scan, with switches to make `test_connection()` fail and to raise mid-fetch
- [x] 1.3 Add fixtures that build tenants the way the API does — org → company → connected `ErpIntegration`, with and without an `ErpCredential` row — never via the runner
- [x] 1.4 Pin current per-integration behaviour before changing anything: a sync against one manually-built integration persists accounts, vendors, invoices, lines and entries into that company

## 2. Discover the work list

- [x] 2.1 Add `connected_integrations(session, integration_id=None)` selecting `ErpIntegration` where `disconnected_at IS NULL`, ordered stably; when `integration_id` is given, narrow to it and raise if it matches nothing
- [x] 2.2 Explicitly do **not** filter on `Company.is_active` — record the reason in a comment so it reads as a decision, not an oversight
- [x] 2.3 Delete `_bootstrap_tenant` entirely
- [x] 2.4 Tests: connected integrations are all returned; a disconnected one is excluded and reappears once reconnected; an inactive company's integration is still included; an unknown `integration_id` raises and creates nothing

## 3. Credentials from the integration row

- [x] 3.1 Add `_connector_config(session, integration)` loading the integration's `ErpCredential` and returning `decrypt_config(...)`, or `{}` when there is no row (the connector then uses its declared field defaults)
- [x] 3.2 Let a decryption failure propagate as that integration's error, with a message naming `WEB_API_CREDENTIAL_ENC_KEY`
- [x] 3.3 Tests: stored credentials reach the connector; a missing credential row yields `{}` and syncs fine; an undecryptable credential fails only its own integration

## 4. Split `run_sync` into per-integration work

- [x] 4.1 Extract the body from `_begin_sync_state` through `_build_summary` into `_sync_one(session, integration, connector, since) -> dict` — a move, not a rewrite; the stage order and every persist call stay as they are
- [x] 4.2 Move connector construction, `authorize()` and `test_connection()` inside the per-integration path so an unreachable ERP is that integration's failure rather than the run's precondition
- [x] 4.3 Have `_sync_one`'s summary carry `company_id`, `erp_type` and `status: "ok"` alongside the existing counts
- [x] 4.4 Tests: `_sync_one` against a fake connector produces the same counts the old flat summary did

## 5. Per-integration watermarks

- [x] 5.1 Add `_resolve_since(state, override)`: explicit override → `SyncState.last_invoice_date` → `None`
- [x] 5.2 Pass the resolved value into the fetch calls in `_sync_one`
- [x] 5.3 Confirm `_finish_sync_state` advances the watermark only on success, and leaves it alone on error
- [x] 5.4 Tests: a second run fetches from the recorded watermark; two integrations at different watermarks each use their own; an explicit `since` overrides both; a failed sync leaves `last_invoice_date` unchanged

## 6. The new `run_sync`

- [x] 6.1 Rewrite `run_sync(*, since=None, integration_id=None) -> dict[str, dict]` as: discover work → for each, build config and connector, `_sync_one` → collect
- [x] 6.2 Wrap each integration in try/except: record the error on its `SyncState` via `_finish_sync_state(..., status="error")` and put `{"status": "error", "error": ...}` in the result, then continue to the next
- [x] 6.3 Return an empty dict when nothing is connected, and log the actionable message ("no connected ERP integrations — create a company with an ERP connection in Settings first")
- [x] 6.4 Delete `run_synthetic`
- [x] 6.5 Tests: two integrations both sync; one failing integration does not stop the other and the earlier one's rows stay committed; an empty database returns `{}` and creates nothing

## 7. CLI

- [x] 7.1 Cut the parser down to `--integration-id` and `--since`; remove `--erp-type`, `--base-url`, `--api-key`, `--org-name`, `--company-name`, and `--no-reset`/`--reset`
- [x] 7.2 Print one block per integration (company, connector, status, counts; error message when failed)
- [x] 7.3 Return a non-zero exit code when any integration failed, so a scheduler sees it
- [x] 7.4 Tests: `main([])` on an empty database exits 0 with the "nothing to sync" message; `main([])` with one failing integration exits non-zero

## 8. Wrap-up

- [x] 8.1 Run `uv run pytest` — all tests pass, including the new `tests/ai_api/`
- [x] 8.2 Update `CLAUDE.md`: the sync-pipeline line becomes "reads every connected `ErpIntegration`, decrypts its credentials, syncs each into its own company"; note the runner now needs `WEB_API_CREDENTIAL_ENC_KEY` when any integration stores credentials, and that companies are created through the frontend, never by the runner
- [x] 8.3 End-to-end check against the real database: start the mock ERP (`uv run uvicorn mock_erp.main:app --port 8001`), run `uv run python -m ai_api.sync.runner`, and confirm the existing `Test` company fills with entries that the Entries page shows — the check the previous change could not complete
