# CLAUDE.md — Project Overview & Guidelines

## Project

**ERP Procurement Agent** — AI that ingests spend data, categorizes it against a
company's own spend tree, detects redundant suppliers, and suggests product-level
savings.

Two pipelines coexist:

1. **PDF pipeline** (original): `InvoiceFlow` — 5 CrewAI stages per PDF invoice
   (extract → verify → research_products → categorize → ledger CSV). Uses Qdrant
   for spend tree retrieval.
2. **Procurement pipeline** (new): batch processes structured transaction data
   from synthetic data or ERP connectors. Same categorization core, but outputs
   to PostgreSQL for aggregation, redundancy detection, and savings suggestions.

The code is split into two packages under `src/` (plus the standalone
`mock_erp/` server):

- **`web_api/`** — the **business domain**: SQLModel ORM + DB session + Alembic,
  ERP connectors, the Streamlit dashboard, and the Clerk-authenticated FastAPI
  backend. Owns persistence and the customer-facing API.
- **`ai_api/`** — the **AI workflows**: the PDF `InvoiceFlow`, RAG/Qdrant
  indexer, agents, the sync pipeline (runner + categorizer), aggregation,
  redundancy detection, and the recommender.

Dependency direction is one-way: **`ai_api` imports the domain from `web_api`**
(ORM models, DB session, connectors); `web_api` never imports `ai_api`.

## Environment

- Managed with Astral `uv`; **Python 3.12**.
- Install: `uv sync`
- Run PDF pipeline: `uv run main.py`
- Run sync pipeline: `python -m ai_api.sync.runner`
- Run web API: `uvicorn web_api.app:app --reload`
- Run dashboard: `streamlit run src/web_api/dashboard/app.py`
- Test: `uv run pytest`
- Migrate DB: `uv run alembic upgrade head`
- Infra: `docker compose up` (Qdrant on :6333, PostgreSQL on :5432)

## Web API auth (Clerk)

- The web API (`web_api/`) is a resource server: it verifies Clerk session JWTs
  against Clerk's JWKS. Set `CLERK_ISSUER` (JWKS URL derives from it) and
  optionally `CLERK_AUDIENCE` in `.env`. `WEB_API_AUTH_DISABLED=true` bypasses
  verification for local dev. See `.env.example`.
- API docs use **Scalar** at `/scalar` (built-in Swagger/ReDoc disabled;
  OpenAPI JSON at `/openapi.json`).
- **CORS** for a browser front-end is opt-in via `WEB_API_CORS_ORIGINS`
  (comma-separated; empty = no cross-origin access).
- **Clerk sync**: `POST /api/v1/webhooks/clerk` receives Svix-signed Clerk events
  (org / membership / user) and applies them idempotently — `organization.deleted`
  **soft-suspends** (retains all data; suspended orgs are blocked from API access
  until restored). Suspending/deleting an org locally (`DELETE /api/v1/organization`,
  admin) propagates to Clerk via the Backend API. Env: `CLERK_WEBHOOK_SIGNING_SECRET`,
  `CLERK_SECRET_KEY`, `WEB_API_CLERK_OUTBOUND_DISABLED` (default true off-prod).
  Register the webhook in the Clerk dashboard → `/api/v1/webhooks/clerk`.

## Web API roles & endpoints

- **Roles** (org role from Clerk): `admin`, `moderator`, `member`, `viewer`.
  Plus a platform-level `User.is_system_admin` set from a Clerk claim named by
  `CLERK_SYSTEM_ADMIN_CLAIM` (default `system_admin`).
- **Write access** to management endpoints = system admin OR org `admin`/`moderator`
  (`require_management`); org-profile updates require system admin OR `admin`
  (`require_org_admin`). `member`/`viewer` are read-only. System admins act
  across organizations.
- **Endpoints**: read — `GET /users/me` (current principal), `/users` (org member
  directory), `/vendors` (the org's referenced suppliers, `?q=`),
  `GET /companies` (`?include_inactive`), `/invoices`,
  `/invoices/{id}`, `/invoice-lines`, `/invoice-lines/{id}/audit`, `/erp-entries`
  (filters: `company_id`/`entry_type`/`voucher_id`/`source_invoice_id`/`status`),
  `/erp-entries/{id}`, `/erp-integrations`, `/erp-integrations/{id}`,
  `/erp-integrations/{id}/accounts`, `/organization`, and **reports** —
  `GET /reports/entries-summary`, `/reports/entries-by-account`,
  `/reports/spend-by-category`, `/reports/spend-by-vendor` (all accept
  `company_id` + `from`/`to`; entries reports also `entry_type`). Manage — `POST /companies`,
  `PATCH /companies/{id}`, `POST /companies/{id}/deactivate|activate`,
  `POST /invoice-lines/{id}/verify` (accept or correct the categorization),
  `PATCH /organization`. **ERP integrations** — `POST /erp-integrations` (with
  credentials), `PATCH /erp-integrations/{id}`, `POST /erp-integrations/{id}/`
  `disconnect|reconnect|test-connection|refresh-accounts`, `PATCH /erp-accounts/{id}`
  (toggle `sync_enabled`/`with_vat`). Integration credentials are stored encrypted
  (`WEB_API_CREDENTIAL_ENC_KEY`, Fernet) and never returned; integrations are
  soft-disconnected. Companies are soft-deactivated, never hard-deleted.

## Categorization lifecycle & audit

- **Result lives on the line.** `InvoiceLine` holds its categorization result
  directly (`level_1/2/3`, `account_code`, `account_name`, `confidence`,
  `rationale`, plus the accepted `spend_category_id`) — there is no separate
  `LineCategorization` table.
- **Line status**: `uncategorized` → `ai_failed` | `ai_categorized` → `verified`.
  The AI sync runner writes the result and sets `ai_categorized`/`ai_failed`; a
  human `POST /invoice-lines/{id}/verify` (management role) sets `verified`,
  optionally correcting the category. `Invoice.status` is a **rollup** of its
  lines (`uncategorized` → `categorized` → `verified`), recomputed in the same
  transaction as any line change (`web_api/rollup.py`).
- **Audit** (`web_api/audit.py` + generic `AuditLog` table): every AI
  categorization and human verify/edit appends an append-only row
  (`entity_type`, `entity_id`, `action`, `actor` — a user id or `system` —,
  field-level `changes`). One table for both invoices and lines.
- **Ground truth is ai_api-only.** Synthetic `gt_*` values live in the
  ai_api-owned `line_ground_truth` store (`ai_api/persistence/`), never on the
  domain line. For real data, a `verified` line's values are treated as truth.

## Vendors (global supplier catalog)

- `Vendor` is a **global** supplier database (`name`, `country_code`,
  `vat_number`, `description`) — **not** company/org-scoped and carrying no ERP
  identity. Identity/dedup on sync is **VAT number, else normalized name**
  (`ai_api/sync/runner.py:_vendor_key`); the same supplier seen by different
  companies collapses onto one row.
- Only `Invoice.vendor_id` references a vendor. Invoice **lines do not** link to
  a vendor, and the vendor holds no back-reference to invoices/lines.

## Reporting

- Read-only, tenant-scoped aggregates live in `web_api/reporting.py` (pure SQL
  `GROUP BY`) behind `web_api/routers/reports.py`. **Ledger sums are
  entry-based** (`entries-summary`, `entries-by-account` over `ErpEntry`);
  **category/vendor spend comes from the invoice layer** (`spend-by-category`
  from categorized lines, `spend-by-vendor` from invoices) — entries carry no
  category/vendor. Money is always **grouped by currency**, never summed across
  currencies. Not built in `ai_api/aggregation` (that stub is pipeline-internal;
  `web_api` can't import `ai_api`).

## ERP entries

- `ErpEntry` is the atomic financial record (raw GL posting), never categorized.
  Its ledger date is `accounting_date` (the posting date; the axis for period
  reporting). It carries **no** direct `erp_integration_id` — the integration is
  reached through its account (`erp_account_id → ErpAccount.erp_integration_id`);
  `company_id` gives tenant scope. The sync scopes an integration's entries by
  joining through `ErpAccount`.

## Model Hosting

- Local vLLM at `http://localhost:8000/v1`, model `google/gemma-4-E4B-it`
  (CrewAI: `hosted_vllm/google/gemma-4-E4B-it`). Configured via `.env`.

## Layout

```text
src/
├── web_api/                  BUSINESS DOMAIN + customer API
│   ├── config.py             domain config: DATABASE_URL + Clerk settings
│   ├── app.py                FastAPI app factory (uvicorn web_api.app:app)
│   ├── auth.py               Clerk JWT verification + JWKS cache
│   ├── deps.py               auth dependency chain + JIT provisioning + tenant scope
│   ├── schemas.py            Pydantic response models
│   ├── audit.py              generic AuditLog helpers (diff + append)
│   ├── rollup.py             Invoice.status rollup from its lines
│   ├── routers/              companies, invoices, invoice-lines (verify + audit)
│   ├── connectors/           ERP connector interface + MockErpConnector
│   ├── dashboard/app.py      Streamlit dashboard (stub)
│   └── db/
│       ├── models/           SQLModel ORM (one file per entity)
│       ├── session.py        engine + session helpers
│       └── migrations/       Alembic
│
└── ai_api/                   AI WORKFLOWS (imports domain from web_api)
    ├── config.py             AI config: LLM factory + vLLM + Qdrant + paths
    ├── models.py             Pydantic schemas (invoice extraction, categorization)
    ├── flow.py               InvoiceFlow (PDF pipeline)
    ├── agents.py             CrewAI agent factories
    ├── grounding.py          categorization guardrail
    ├── web_context.py        buyer + product web context
    ├── ledger.py             CSV output (PDF pipeline)
    ├── pdf_loader.py         PDF text extraction
    ├── parsing.py            LLM JSON repair
    ├── rag/indexer.py        Qdrant vector store (spend tree retrieval)
    ├── synthdata/            synthetic invoice generator
    ├── persistence/          ai_api-owned store: line_ground_truth (synthetic gt_*)
    ├── sync/runner.py        pipeline orchestrator (connect→fetch→persist→categorize)
    ├── sync/categorizer.py   deterministic keyword categorizer (stub for Qdrant+LLM)
    ├── aggregation/engine.py SQL rollups (stub)
    ├── redundancy/detector.py vendor overlap detection (stub)
    └── procurement_agent/recommender.py  savings suggestions (stub)

mock_erp/                     standalone mock ERP API server (unchanged)
```
