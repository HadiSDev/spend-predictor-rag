# monorepo-layout Specification

## Purpose
TBD - created by archiving change move-apps-into-apps-dir. Update Purpose after archive.
## Requirements
### Requirement: Every runnable app lives under apps/

The repository SHALL place each runnable application in its own directory under
`apps/`: `apps/web` (the frontend), `apps/web-api` (the business domain and
customer API, import name `web_api`), `apps/ai-api` (the AI workflows, import
name `ai_api`) and `apps/mock-erp` (the standalone mock ERP server, import name
`mock_erp`). The repository root SHALL NOT contain application source: no `src/`,
no `frontend/`, no `mock_erp/`. The root keeps only workspace-level files
(workspace manifest, lockfile, compose file, docs, OpenSpec, shared `data/`).

#### Scenario: Old locations are gone

- **WHEN** the repository root is listed after the change
- **THEN** it contains `apps/` with exactly `web`, `web-api`, `ai-api` and
  `mock-erp`, and contains no `src/`, `frontend/` or `mock_erp/` directory

#### Scenario: Import names are unchanged

- **WHEN** application code imports `web_api`, `ai_api` or `mock_erp`
- **THEN** the import resolves without modification to the import statement

### Requirement: Python apps are members of one uv workspace

Each Python app SHALL have its own `pyproject.toml` using a `src/` layout. The
root `pyproject.toml` SHALL be a virtual workspace root declaring the three
Python apps as members, with a single `uv.lock` and a single `.venv` at the
root. A plain `uv sync` at the root SHALL install every member in editable mode.
The root SHALL NOT list the members in a group named `dev`: `--package <app>
--group dev` unions every `dev` group in the workspace, so doing so would pull
every member into a single-app install.

#### Scenario: One sync installs everything

- **WHEN** a developer runs `uv sync` at the repository root
- **THEN** `web_api`, `ai_api` and `mock_erp` are all importable from the root
  `.venv`, and editing a source file takes effect with no reinstall

### Requirement: The ai-api → web-api dependency direction is enforced by packaging

`ai-api` SHALL declare `web-api` as a workspace dependency. `web-api` SHALL NOT
declare `ai-api`, directly or transitively, in its runtime dependencies or its
dependency groups. `mock-erp` SHALL depend on neither. Each manifest SHALL list
only the third-party packages its own code imports.

#### Scenario: web-api installs without the AI stack

- **WHEN** `web-api` is installed on its own into a fresh environment
  (`uv sync --package web-api --no-default-groups --group dev`)
- **THEN** `crewai`, `sentence-transformers` and `qdrant-client` are not
  installed, and `import ai_api` fails

#### Scenario: ai-api reaches the domain

- **WHEN** `ai-api` is installed on its own
- **THEN** `web_api` is installed with it and `ai_api.sync.runner` imports
  successfully

### Requirement: Each app owns its test suite

Each Python app SHALL keep its tests in `apps/<app>/tests/`, and a test SHALL
live in the app whose code it tests. `apps/<app>/tests/` SHALL NOT be a Python
package (no `__init__.py`), because two top-level packages named `tests` collide
in one pytest session. Helpers that tests import by name SHALL live in a
uniquely named `<app>_testkit.py` that pytest's `pythonpath` exposes. A `web-api` test session SHALL NOT import
`ai_api`, including through an autouse fixture. `mock-erp` MAY appear in
`web-api`'s dev dependency group, because connector tests drive the mock ERP
in-process. Running `uv run pytest` at the repository root SHALL collect and
run every app's suite, and running `uv run pytest` inside one app directory
SHALL run only that app's suite.

#### Scenario: Root run covers every app

- **WHEN** `uv run pytest` is run at the repository root
- **THEN** the tests of `web-api`, `ai-api` and `mock-erp` are all collected,
  and the pass/fail count equals the pre-move count

#### Scenario: web-api suite is AI-free

- **WHEN** the `web-api` suite runs in an environment where `ai_api` is not
  installed
- **THEN** every `web-api` test is collected and none fails on an import of
  `ai_api`

### Requirement: Shared runtime data resolves to the repository root

`ai_api.config.PROJECT_ROOT` SHALL resolve to the repository root, not to
`apps/ai-api`, so that `data/`, `output/` and `chroma_db/`, and the env-var
defaults derived from them, keep their current locations. `.env` at the
repository root SHALL keep configuring both APIs.

#### Scenario: Data paths unchanged

- **WHEN** `ai_api.config` is imported with no path overrides in the
  environment
- **THEN** `CHART_OF_ACCOUNTS_PATH` is `<repo>/data/chart_of_accounts.csv` and
  `LEDGER_PATH` is `<repo>/output/ledger.csv`

### Requirement: Each app builds and runs from its own directory

The mock ERP's Docker image SHALL build from `apps/mock-erp` as its context and
install only the `mock-erp` package. Alembic SHALL be configured from
`apps/web-api/alembic.ini`, with the script location given relative to that file
(`%(here)s`), so migrations run from any working directory via `-c`. The
frontend SHALL keep its bun project, lockfile and scripts unchanged inside
`apps/web`.

#### Scenario: Mock ERP image excludes the AI stack

- **WHEN** `docker compose build mock-erp-api` runs
- **THEN** the build context is `apps/mock-erp`, and the image contains neither
  `crewai` nor `web_api`

#### Scenario: Migrations run from the root

- **WHEN** `uv run alembic -c apps/web-api/alembic.ini upgrade head` runs at the
  repository root
- **THEN** the migration chain applies exactly as `uv run alembic upgrade head`
  did before the move, and `apps/web-api/tests/db/test_migrations.py` passes

