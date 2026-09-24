## Context

The current layout (see proposal) has one Python project that installs both
`web_api` and `ai_api` from `src/`, plus `mock_erp/` as a third package in the
same wheel (`[tool.hatch.build.targets.wheel] packages = [...]`). The frontend
sits separately in `frontend/`. Relevant couplings found while surveying:

- `web_api` never imports `ai_api` in code (only in comments), so the split is
  clean at the source level.
- `mock_erp` imports neither API.
- **Tests are not clean.** The root `tests/conftest.py` has two autouse
  fixtures: `offline_fx`, which imports `web_api.config`, and
  `offline_categorizer`, which imports `ai_api.sync.llm_categorizer`. The
  second one runs for every `tests/web_api/*` test. Root-level tests mix all
  three packages: `test_mock_erp.py` and `test_connectors.py` drive `mock_erp`
  through `web_api`'s `MockErpConnector`, and `test_sync_runner.py` imports both
  APIs.
- **Path arithmetic.** `ai_api/config.py` has `PROJECT_ROOT = parents[2]`,
  `web_api/app.py`'s `__main__` has a reloader `parents[1]`,
  `tests/web_api/test_migrations.py` has `REPO_ROOT = parents[2]` plus
  `PYTHONPATH=src`, `scripts/*` use `parents[1]`, and `alembic.ini` has
  `script_location = src/web_api/db/migrations` and `prepend_sys_path = src`.
- `load_dotenv()` with no arguments walks up from the calling file, so a root
  `.env` is still found from `apps/*/src/...`.
- The frontend references nothing outside its own directory. Its `.env` and
  `node_modules/` are gitignored.
- Several agents share this working tree (see memory: work on main, never
  revert shared files).

## Goals / Non-Goals

**Goals:**
- Match the `monorepo-layout` spec: `apps/{web,web-api,ai-api,mock-erp}`.
- Make the `ai-api → web-api` direction a packaging constraint.
- Give each app a dependency set and test suite of its own.
- Keep every import name, runtime behaviour, data location and test outcome
  identical.

**Non-Goals:**
- Any frontend tooling change (no Turborepo or bun workspaces). `apps/web` is
  moved, not re-plumbed.
- Extracting a shared Python library. `ai_api` keeps importing the domain from
  `web_api` as it does today.
- Rewriting historical documents: `docs/superpowers/plans/*` and
  `openspec/changes/archive/*` describe the past and keep old paths.
- Upgrading or removing any dependency.

## Decisions

**1. uv workspace with a virtual root.** The root `pyproject.toml` keeps no
`[project]`. It has only `[tool.uv.workspace] members = [...]`, a `dev` group
(`pytest`), an `apps` group listing the members, both as `default-groups`, and
`[tool.pytest.ini_options]`. *Found during apply:* the members must **not** go
in `dev`. `uv sync --package web-api --group dev` unions every group named `dev`
across the workspace, so members listed there installed crewai into a
"web-api only" environment.
Members declare `ai-api = ["web-api"]` through
`[tool.uv.sources] web-api = { workspace = true }`. The `anls` git source moves
into `ai-api`'s `[tool.uv.sources]`.
- *Alternative: separate projects with separate locks.* Rejected: three venvs
  and version drift between two packages that share SQLModel models at runtime.
- *Alternative: keep one pyproject and just move folders.* Rejected by the user,
  and it does not enforce the dependency direction.

**2. Distribution names are hyphenated, import names are not.** `web-api` →
`web_api`, `ai-api` → `ai_api`, `mock-erp` → `mock_erp`. Directory names match
the distribution names. Hatchling's `src/` layout finds the package without an
explicit `packages` list.

**3. `mock_erp` gets a `src/` layout too** (`apps/mock-erp/src/mock_erp/`),
for consistency. Its `Dockerfile` moves to `apps/mock-erp/Dockerfile`, copies
its own `pyproject.toml` and `src/`, and runs `pip install .`. `docker-compose.yml`
changes to `build: { context: apps/mock-erp }`. The image stops installing the
AI stack.

**4. Dependency split, derived from actual imports** (surveyed with grep over
`import`):

| Package | web-api | ai-api | mock-erp |
|---|---|---|---|
| fastapi, uvicorn[standard] | ✓ | via web-api | ✓ |
| sqlmodel, alembic, psycopg2-binary | ✓ | via web-api | |
| pyjwt[crypto], svix, scalar-fastapi, httpx | ✓ | via web-api | |
| cryptography (Fernet) | ✓ (explicit; today transitive) | | |
| streamlit (dashboard) | ✓ | | |
| python-dotenv, pydantic | ✓ | ✓ | ✓ (pydantic) |
| crewai, crewai-tools, qdrant-client, sentence-transformers | | ✓ | |
| pdfplumber, json-repair, ddgs, faker, anls, pypdfium2/Pillow | | ✓ | |
| weasyprint, jinja2 | | ✓ | ✓ |
| reportlab (dev) | | ✓ dev | |
| bespokelabs-curator (`live` group) | | ✓ group | |

The implementer re-runs the import survey before writing the manifests. Any
import found in a package but missing from its manifest is a failure of this
step, not a later fix. A transitive dependency that code imports directly
(`cryptography`, `PIL`, `pypdfium2`) is made explicit in the manifest of the
package that imports it.

**5. Tests split by the package under test, with fixtures duplicated rather
than shared.**
- `tests/web_api/**` goes to `apps/web-api/tests/`. Root `test_billy_connector.py`,
  `test_connector_http.py`, `test_connectors.py`, `test_mock_erp.py`,
  `test_spend_category.py` and `fixtures/billy/` go there too, since they test
  `web_api` connectors and models.
- `tests/ai_api/**`, `tests/synthdata/**` and the root PDF-pipeline tests
  (`test_agents`, `test_config`, `test_flow`, `test_grounding`, `test_indexer`,
  `test_ledger`, `test_models`, `test_parsing`, `test_pdf_loader`,
  `test_web_context`, `test_smoke`, `test_sync_runner`) go to
  `apps/ai-api/tests/`. Existing subfolders are kept (for example
  `tests/pdf_pipeline/` and `tests/synthdata/`), so two files named
  `test_sync_runner.py` cannot collide.
- `mock-erp`'s own behaviour is already covered by `test_mock_erp.py`, which
  needs the connector, so `apps/mock-erp/tests/` stays minimal: an import smoke
  test plus the data generators' determinism, if any such test exists today.
- Root `conftest.py` is dissolved. `offline_fx` goes into **both**
  `web-api` and `ai-api` conftests, since each app's session needs FX forced off.
  `offline_categorizer` goes **only** into `ai-api`'s conftest. The
  `mock_erp_connector` fixture goes to `web-api`'s conftest.
- *Why duplicate `offline_fx` instead of a shared test package?* It is about
  eight lines, and a shared `conftest` at the root is exactly what leaked
  `ai_api` into the web suite. A test-utils package would be a fourth workspace
  member for one fixture.
- Pytest runs with `--import-mode=importlib`, and the top-level
  `tests/__init__.py` files are removed, so that three directories named `tests`
  do not clash as the same top-level package. *Found during apply:* importlib
  mode alone does **not** fix this. With the markers kept, both conftests
  register as `tests.conftest` and the session aborts, and neither
  `consider_namespace_packages` nor an `__init__.py` at the app root helps
  (`web-api` is not an identifier). Removing the markers breaks the tests' 12
  relative imports (`from .conftest import auth`, `from .test_webhooks import
  post_event`, and others). So those helpers move to `web_api_testkit.py` and
  `ai_api_testkit.py`, which are uniquely named and exposed through pytest's
  `pythonpath`. Subpackages (`parsers/`, `synthdata/`) keep their markers,
  since their names are already unique.
- *Found during apply:* the new collection order runs the old root tests
  (`pdf_pipeline/`) **before** the `test_*.py` files they used to follow. The
  old root `test_sync_runner.py` re-registered the process-global `"fake"`
  connector name, swapping the connector under 25 later ai-api tests. It had
  been order-dependent all along, and running last hid that. It now registers
  as `"fake-entry-first"`. The root `testpaths` lists the three app test dirs. Each
  app's `pyproject.toml` has its own `[tool.pytest.ini_options]`, so running
  pytest inside an app runs only that app's suite. `pythonpath = ["src"]` is
  dropped, because editable installs make it unnecessary.
- No test imports from `tests.…` today (checked), so removing the package
  markers breaks nothing. A future shared helper goes into the app's conftest.

**6. `PROJECT_ROOT` keeps pointing at the repository root.** It becomes
`Path(__file__).resolve().parents[4]` (`ai_api` → `src` → `ai-api` → `apps` →
root), with the arithmetic spelled out in a comment. `test_config.py` already
asserts that the root contains `data/`, and gains an assertion that
`PROJECT_ROOT / "apps"` exists, which pins the value.
- *Alternative: search upward for a marker (`uv.lock`).* Rejected: it works
  equally well from a non-editable install in a container, but `data/` is not
  shipped in any image anyway. The env-var overrides already cover deployment,
  and a fixed depth is easier to read than a search loop.

**7. Alembic config moves into `apps/web-api/`.** It uses
`script_location = %(here)s/src/web_api/db/migrations` and drops
`prepend_sys_path` (editable install). The canonical command becomes
`uv run alembic -c apps/web-api/alembic.ini upgrade head`, and the migration
test uses the same path. Keeping `alembic.ini` at the root was rejected because
it is a web-api artifact. The `-c` flag is a small cost, and it is written into
`CLAUDE.md`.

**8. Scripts follow their dependencies.** `billy_fixtures.py` (writes
web-api test fixtures) and `doc_baseline.py` (imports only `web_api`) go to
`apps/web-api/scripts/`. `generate_sample_invoice.py` (writes
`data/invoices`, reportlab) goes to `apps/ai-api/scripts/`. Their `parents[n]`
paths are recomputed. `main.py` goes to `apps/ai-api/main.py`, and can also be
exposed as a `[project.scripts]` entry (`invoice-flow`).

**9. The move is done with `git mv` in one commit, content edits in a second.**
Keeping pure renames separate from edits keeps git's rename detection at 100%.
`git log --follow`, `git blame` and rebasing an in-flight branch across the move
all depend on it. Untracked `frontend/.env` and `frontend/node_modules` are
moved with plain `mv` after the `git mv`.

## Risks / Trade-offs

- [Open branches and worktrees conflict with a whole-tree rename] → Land the
  move when the tree is quiet. Announce it in the commit message. Keep the
  rename commit edit-free so git carries other branches' edits across it on
  rebase.
- [`node_modules` breaks when moved (absolute paths in `.bin` shims or bun's
  cache links)] → Verify with `./node_modules/.bin/vitest run` in `apps/web`.
  If it fails, the developer runs `bun install` themselves. Per project rules,
  never pnpm or npm, and the agent does not run installs.
- [A dependency missed in the split surfaces only at runtime, in an untested
  path such as the Streamlit dashboard] → The import survey in Decision 4 is
  mechanical. Also run each module's `python -c "import …"` from an env with
  only that member installed (`uv sync --package <name>`).
- [SQLite-only test suite misses a PostgreSQL-only Alembic path break] →
  `test_migrations.py` runs the chain against a real PostgreSQL when one is
  reachable (port 5433 locally per memory). Run it before the commit.
- [Local tooling outside git (`.claude/settings.json`, IDE run configs, shell
  history, the dev-server commands the user runs)] → List the new commands in
  the commit message and in CLAUDE.md's Environment section.
- [Duplicated `offline_fx` fixture can drift] → Accepted. It is small and its
  docstring states the rule it enforces.

## Migration Plan

1. Confirm a clean tree and no in-flight agent edits to `src/`, `frontend/`,
   `mock_erp/` or `tests/`.
2. Commit A (renames only): `git mv` everything into `apps/`.
3. Commit B (edits): manifests, workspace root, conftests, path arithmetic,
   alembic, Dockerfile, compose, docs. Run `uv lock` and `uv sync`, then the
   full test suite and the frontend's vitest/lint.
4. The developer moves their own untracked state (`frontend/.env`, if not
   already moved) and updates their run commands.

Rollback: revert commit B then commit A. No data, schema or external state is
touched.

## Open Questions

- Should the root keep thin convenience wrappers (for example a `Makefile` or
  `justfile` with `web`, `api`, `sync` and `migrate` targets) so the longer
  commands stay short? The default is no: out of scope, and easy to add later.
