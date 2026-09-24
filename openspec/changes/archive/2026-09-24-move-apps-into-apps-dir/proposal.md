## Why

The repository root currently holds four runnable things side by side: the
frontend in `frontend/`, both Python APIs in one `src/` with a single
`pyproject.toml`, and `mock_erp/` next to them. The rule that matters most
architecturally is "`ai_api` imports `web_api`, and `web_api` never imports
`ai_api`". Today nothing enforces it, because both packages share one install,
one dependency list and one test session. A root-level `conftest.py` already
imports `ai_api` into every `web_api` test. The web API also installs CrewAI,
sentence-transformers and weasyprint that it never uses, and the mock ERP's
Docker image runs `pip install .` against the whole project. Putting each app in
its own directory under `apps/`, with its own manifest, makes the dependency
direction a packaging fact rather than a convention, and gives each app a
dependency set and test suite that belong to it alone.

## What Changes

- **BREAKING (paths)**: `frontend/` moves to `apps/web/`. Its contents are
  unchanged: same bun project, same `bun.lock`, same scripts.
- **BREAKING (paths)**: `src/web_api/` moves to `apps/web-api/src/web_api/`, with
  its own `pyproject.toml` (distribution `web-api`), its tests, `alembic.ini`
  and the scripts that only touch the domain.
- **BREAKING (paths)**: `src/ai_api/` moves to `apps/ai-api/src/ai_api/`, with its
  own `pyproject.toml` (distribution `ai-api`, **depending on `web-api`**), its
  tests and the PDF-pipeline entry point `main.py`.
- **BREAKING (paths)**: `mock_erp/` moves to `apps/mock-erp/src/mock_erp/`, with
  its own `pyproject.toml` (distribution `mock-erp`) and a Dockerfile that
  builds only the mock ERP.
- The root `pyproject.toml` becomes a **virtual uv workspace root**:
  `[tool.uv.workspace] members = ["apps/web-api", "apps/ai-api", "apps/mock-erp"]`.
  One `uv.lock` and one `.venv` remain at the root.
- Dependencies are split by actual imports. `web-api` gets FastAPI, SQLModel,
  Alembic, Clerk/JWT, svix, httpx and Streamlit. `ai-api` gets CrewAI, Qdrant,
  sentence-transformers, pdfplumber, weasyprint and the synthdata stack.
  `mock-erp` gets FastAPI, Jinja2 and weasyprint.
- The single `tests/` tree is split per app. Shared autouse fixtures are
  duplicated where each app needs them, so a `web-api` test session never
  imports `ai_api`. `uv run pytest` at the root still runs every suite.
- `ai_api.config.PROJECT_ROOT` still resolves to the **repository root**, so
  `data/`, `output/` and `chroma_db/` stay where they are, and so do their env
  overrides.
- Import names are **unchanged**: `web_api`, `ai_api` and `mock_erp`. No Python
  import statement in application code changes.
- The living docs are updated: `CLAUDE.md`, `README.md`,
  `openspec/config.yaml` context, and `.gitignore`. So are `docker-compose.yml`
  and the run commands. Archived changes and historical plans under `docs/` are
  left as they are.

## Capabilities

### New Capabilities
- `monorepo-layout`: where each app lives, what each app's manifest may depend
  on (including the enforced `ai-api → web-api` direction), how the workspace
  installs and tests them, and where shared runtime data resolves.

### Modified Capabilities
- `frontend-ui-library`: the component barrel path in its requirements changes
  from `frontend/src/components/ui/` to `apps/web/src/components/ui/`.

## Impact

- **Every path-based command changes.** This covers `uvicorn`, `streamlit`,
  `alembic` (now run with `-c apps/web-api/alembic.ini`), the frontend's `bun`
  scripts (`cd apps/web`), `docker compose` (the mock-erp build context), and
  any IDE or run configuration pointing at `src/` or `frontend/`.
- **Untracked local state has to move by hand.** `git mv` will not carry
  `frontend/.env` or `frontend/node_modules`. Both must be moved physically, and
  a frontend dependency reinstall (`bun install`, run by the developer) is the
  fallback if `node_modules` does not survive the move.
- **Concurrent work in this repo.** Several agents and worktrees share this
  repository, and every open branch that touches `src/` or `frontend/` will
  conflict. The move should land as one commit at a quiet moment, with rename
  detection intact so `git log --follow` and rebases still work.
- Dependencies: `uv.lock` is regenerated. No package versions change and no
  package is added or removed; each dependency just moves to the manifest that
  uses it.
- No runtime behaviour, API, schema or migration changes.
