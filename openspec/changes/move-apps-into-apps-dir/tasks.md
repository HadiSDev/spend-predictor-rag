## 1. Preflight

- [x] 1.1 Confirm `git status` is clean and no other agent or worktree has uncommitted edits under `src/`, `frontend/`, `mock_erp/`, `tests/` or `scripts/`. Stop and ask if any does.
- [x] 1.2 Record the baseline: `uv run pytest -q` pass/fail counts, plus `./node_modules/.bin/vitest run` and `./node_modules/.bin/eslint` results in `frontend/`
- [x] 1.3 Re-run the import survey (third-party imports per package, see design Decision 4) and save the per-package list to use when writing the manifests

## 2. Renames only (commit A)

- [x] 2.1 `git mv frontend apps/web`
- [x] 2.2 `git mv src/web_api apps/web-api/src/web_api`, and `git mv src/ai_api apps/ai-api/src/ai_api`
- [x] 2.3 `git mv mock_erp apps/mock-erp/src/mock_erp`, then `git mv apps/mock-erp/src/mock_erp/Dockerfile apps/mock-erp/Dockerfile`
- [x] 2.4 Move web-api tests: `tests/web_api/*` and root `test_billy_connector.py`, `test_connector_http.py`, `test_connectors.py`, `test_mock_erp.py`, `test_spend_category.py`, `fixtures/` → `apps/web-api/tests/`
- [x] 2.5 Move ai-api tests: `tests/ai_api/*` → `apps/ai-api/tests/`, `tests/synthdata/` → `apps/ai-api/tests/synthdata/`, and the root PDF-pipeline tests (`test_agents`, `test_config`, `test_flow`, `test_grounding`, `test_indexer`, `test_ledger`, `test_models`, `test_parsing`, `test_pdf_loader`, `test_web_context`, `test_smoke`, `test_sync_runner`) → `apps/ai-api/tests/pdf_pipeline/`
- [x] 2.6 Move scripts: `billy_fixtures.py` and `doc_baseline.py` → `apps/web-api/scripts/`, `generate_sample_invoice.py` → `apps/ai-api/scripts/`, `main.py` → `apps/ai-api/main.py`, `alembic.ini` → `apps/web-api/alembic.ini`
- [x] 2.7 Physically `mv` the untracked `frontend/.env` and `frontend/node_modules` into `apps/web/`
- [x] 2.8 Verify `git status` shows only renames (`R100`) and that `src/`, `frontend/`, `mock_erp/`, `tests/` and `scripts/` are gone. Commit A as a rename-only commit.

## 3. Workspace and manifests

- [x] 3.1 Rewrite the root `pyproject.toml` as a virtual workspace root: `[tool.uv.workspace] members`, shared `[dependency-groups] dev = ["pytest"]`, and `[tool.pytest.ini_options]` with `testpaths` for the three app test dirs and `addopts = "--import-mode=importlib"`
- [x] 3.2 Write `apps/web-api/pyproject.toml` (hatchling, src layout) with the web-api deps from 1.3, including an explicit `cryptography` and `streamlit`, and a dev group containing `mock-erp` as a workspace source
- [x] 3.3 Write `apps/ai-api/pyproject.toml` with the ai-api deps from 1.3 plus `web-api = { workspace = true }`, the `anls` git source, a dev group with `reportlab`, the `live` group, and an `invoice-flow` script entry for `main`
- [x] 3.4 Write `apps/mock-erp/pyproject.toml` with only fastapi, uvicorn, pydantic, jinja2 and weasyprint
- [x] 3.5 Add a per-app `[tool.pytest.ini_options]` (importlib mode) to each member so that `uv run pytest` inside an app runs only that suite
- [x] 3.6 Run `uv lock` and `uv sync`. Confirm that no package version changed in the `uv.lock` diff other than the workspace members themselves.

## 4. Path arithmetic and config

- [x] 4.1 `ai_api/config.py`: `PROJECT_ROOT = parents[4]`, with a comment spelling out the hops. Extend `test_config.py` to assert that `PROJECT_ROOT / "apps"` and `PROJECT_ROOT / "data"` exist.
- [x] 4.2 `web_api/app.py` `__main__`: point the reloader's watch dir at `apps/web-api/src`, still never the repository root
- [x] 4.3 `apps/web-api/alembic.ini`: `script_location = %(here)s/src/web_api/db/migrations`, and drop `prepend_sys_path`
- [x] 4.4 `test_migrations.py`: derive `ALEMBIC_INI` from the app dir, drop the `PYTHONPATH=src` env override, and keep `cwd` at a directory from which `-c` resolves
- [x] 4.5 Recompute `parents[n]` in the moved scripts (`billy_fixtures.py` writes to `apps/web-api/tests/fixtures/billy`, and `generate_sample_invoice.py` writes to the root `data/invoices`)
- [x] 4.6 Update any comment that names an old path (`mock_erp/documents.py`'s pointer to the synthdata renderer, `.env.example`'s "`src/` reads this")

## 5. Test fixtures split

- [x] 5.1 Delete the root `tests/conftest.py` and the top-level `apps/*/tests/__init__.py`. Move helpers that tests import by name into `web_api_testkit.py` and `ai_api_testkit.py`.
- [x] 5.2 `apps/web-api/tests/conftest.py`: merge the existing web_api conftest with `offline_fx` and the `mock_erp_connector` fixture. It must contain no `ai_api` import.
- [x] 5.3 `apps/ai-api/tests/conftest.py`: merge the existing ai_api conftest with `offline_fx` and `offline_categorizer`
- [x] 5.4 Add `apps/mock-erp/tests/test_smoke.py` (the app imports and `/health` or the root route responds through `TestClient`)
- [x] 5.5 Verify the direction in a scratch env (`UV_PROJECT_ENVIRONMENT=… uv sync --package web-api --no-default-groups --group dev`): `apps/web-api` tests pass and `import ai_api` fails. Do the same for ai-api and mock-erp.

## 6. Build and run surfaces

- [x] 6.1 Rewrite `apps/mock-erp/Dockerfile` to copy only its own `pyproject.toml` and `src/`, and install that. Set the `docker-compose.yml` build context to `apps/mock-erp`.
- [x] 6.2 Confirm that `docker compose build mock-erp-api` succeeds and the image has no `crewai` (skip with a note if Docker is unavailable)
- [x] 6.3 In `apps/web`, run `./node_modules/.bin/vitest run`, `./node_modules/.bin/eslint` and `./node_modules/.bin/tsc --noEmit`. If `node_modules` is broken by the move, stop and ask the user to run `bun install`; never run an installer.

## 7. Docs

- [x] 7.1 `CLAUDE.md`: rewrite the Environment commands (uvicorn, streamlit, alembic `-c`, pytest, runners, frontend under `apps/web`), the package-split paragraph, the Layout tree, and every `src/…` or `frontend/…` path mention
- [x] 7.2 `README.md`, `.gitignore` (frontend-relative entries if any), and `openspec/config.yaml` context line
- [x] 7.3 Non-requirement prose in living specs: the Project Structure blocks in `openspec/specs/mock-erp-api/spec.md` and `openspec/specs/erp-connector-interface/spec.md`. The `frontend-ui-library` path is handled by this change's delta spec at archive time.
- [x] 7.4 Leave `docs/superpowers/plans/*` and `openspec/changes/archive/*` untouched

## 8. Verify and land (commit B)

- [x] 8.1 `uv run pytest -q` at the root: the counts match the 1.2 baseline exactly. `uv run pytest` inside each app runs only that app's suite.
- [x] 8.2 Run the migration test against a real PostgreSQL (5433 locally) so it runs rather than skips
- [x] 8.3 Import smoke check: `web_api.app`, `web_api.dashboard.app`, `ai_api.sync.runner`, `ai_api.documents.runner`, `ai_api.enrichment.runner`, `ai_api.suggestions.runner`, `ai_api.flow` and `mock_erp.main` each import cleanly
- [x] 8.4 `grep -rnE "(^|[^/])src/(web_api|ai_api)|\bfrontend/|\bmock_erp/"` across tracked files, excluding the archive and historical plans, returns nothing
- [x] 8.5 Commit B, listing the new run commands in the message. Hand the user the dev-server commands rather than launching them.
