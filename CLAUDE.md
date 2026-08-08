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
- Run sync pipeline: `python -m ai_api.sync.runner` (syncs **every connected
  `ErpIntegration`**; see below)
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
  `GET /companies` (`?include_inactive`; each carries its `base_currency`), `/invoices`,
  `/invoices/{id}`, `/invoice-lines`, `/invoice-lines/{id}/audit`, `/erp-entries`
  (filters: `company_id`/`entry_type`/`voucher_id`/`source_invoice_id`/`status`/
  `from`/`to`/`vendor_id` — `from`/`to` bound `accounting_date`, and `vendor_id`
  resolves through the entry's source invoice, so unlinked postings never match;
  ordered `accounting_date` desc with undated last, then `voucher_id`, then `id`,
  so a voucher's postings stay adjacent and pagination is stable),
  `/erp-entries/vouchers` (the same rows **grouped by voucher**, paginated over
  groups so a voucher's postings are never split across a page; a null
  `voucher_id` forms a group of one, and a group's `currency`/vendor are null
  when its entries disagree). **Both entry listings exclude `entry_type=payment`**
  (`_EXCLUDED_ENTRY_TYPES` in `_entry_conditions()`): a payment settles an
  invoice already accounted for, so it is noise in a spend tool. It is a product
  rule, not a default — `?entry_type=payment` returns an empty page — and it is
  narrow: `credit_note` and `journal_entry` both move real spend and stay.
  `GET /erp-entries/{id}` is **not** gated (a lookup, not a listing), and
  `reporting.py` is untouched, so the reports stay ledger-complete; that is why
  the frontend filters `payment` out of its entry-type options
  (`listableEntryTypes`). Then `/erp-entries/{id}`, `/erp-integrations`, `/erp-integrations/{id}`,
  `/erp-integrations/{id}/accounts` (the chart of accounts; readable by any
  authenticated member, writes are management-gated), `/erp-types` (the connector catalog:
  which ERP systems this deployment supports and the credential fields each
  declares — authenticated, not management-gated), `/organization`, and **reports** —
  `GET /reports/entries-summary`, `/reports/entries-by-account`,
  `/reports/spend-by-category`, `/reports/spend-by-vendor` (all accept
  `company_id` + `from`/`to`; entries reports also `entry_type`). Manage — `POST /companies`
  (**requires a `base_currency` and an `integration` block**: the company, its
  `ErpIntegration`, and its encrypted credential are written in one transaction,
  so a company is never left without an ERP connection; the response is the
  company plus its integration),
  `PATCH /companies/{id}`, `POST /companies/{id}/deactivate|activate`,
  `POST /companies/{id}/recompute-fx` (rewrite stored base amounts),
  `POST /invoice-lines/{id}/verify` (accept or correct the categorization),
  `PATCH /organization`. **ERP integrations** — `POST /erp-integrations` (with
  credentials), `PATCH /erp-integrations/{id}`, `POST /erp-integrations/{id}/`
  `disconnect|reconnect|test-connection|refresh-accounts`, `PATCH /erp-accounts/{id}`
  (toggle `sync_enabled`/`with_vat`). **`sync_enabled` and `with_vat` are
  customer settings, not ERP metadata**: the ERP's value seeds a newly
  discovered account, and from then on neither `refresh-accounts` nor the sync
  runner may overwrite them — both upsert sites refresh only name, type, parent
  and `is_active`. `with_vat` records whether an account is *assumed* VAT-
  inclusive, which is what lets reconciliation tell a VAT difference from a
  total difference; it recomputes no stored amount. Managed from
  `/settings/companies/$companyId/accounts` in the frontend. Both creation paths share
  `web_api/integrations.py` (`provision_integration` adds without committing, so
  the caller owns the transaction) and validate credentials against the
  connector's declared `credential_fields` — required ones must be present,
  undeclared keys are rejected. An integration's `erp_type` is **fixed once
  connected** (`PATCH` takes label + credentials only), and credentials are
  write-only: the API returns no values, and supplying `credentials` replaces
  the whole map, so a client can only replace them wholesale, never edit one. Integration credentials are stored encrypted
  (`WEB_API_CREDENTIAL_ENC_KEY`, Fernet) and never returned; no credential row is
  written when none are supplied, so a connector whose fields all have defaults
  needs no encryption key. Integrations are soft-disconnected. Companies are
  soft-deactivated, never hard-deleted.

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
  category/vendor. Money is always **grouped by a currency column**, never summed
  across currencies. Not built in `ai_api/aggregation` (that stub is
  pipeline-internal; `web_api` can't import `ai_api`).
- Every report — and `GET /erp-entries/vouchers`, whose group totals are also
  sums — takes **`currency_mode=base|original`, defaulting to `base`**: `base`
  groups by the stored `base_currency` and sums the converted amounts (one row
  per dimension, in the customer's currency); `original` groups by the as-posted
  `currency` and reproduces the pre-conversion behaviour exactly. Unconverted
  rows have a null `base_currency`, so in base mode they form their own row —
  null currency, zero totals, `unconverted_count` set — rather than being folded
  into a total they don't belong in or dropped so it understates spend.

## Currency conversion (company base currency)

- **Every `Company` has a `base_currency`** (ISO 4217, required at creation,
  editable in Settings). It is a customer setting like `sync_enabled`: no
  connector, sync, or refresh may overwrite it.
- **Amounts are converted at the rate in force on the transaction's own date**,
  never today's — `Invoice.invoice_date`, `ErpEntry.accounting_date`, and a line
  follows its invoice. `Invoice`, `InvoiceLine` and `ErpEntry` each store
  `base_currency`, base amount column(s), `fx_rate` and `fx_rate_date` **beside
  the as-posted columns, which are never rewritten** — they are the evidence.
  `fx_rate` is base-per-1-posted, so `base = amount × fx_rate` reproduces the
  stored figure exactly. A same-currency row still converts, at rate 1.
- **No date, no rate, or no network ⇒ stored unconverted** (all base fields
  null), never converted at a substitute rate. FX failures never fail a sync:
  the ledger data lands and the watermark still advances.
- `web_api/fx/` — `provider.py` (ECB daily reference rates via Frankfurter,
  behind a one-method seam tests stub), `service.py` (`FxService`: rate
  resolution, per-run memo, row conversion), `recompute.py`, `backfill.py`.
  Rates cache in `fx_rates` **against EUR**, so any pair is derived as
  `rate(EUR→B)/rate(EUR→A)`; a non-publication date (weekend/holiday) resolves
  **backwards** and the row records `published_date`, so a Saturday is cached
  without passing a lookup date off as a publication.
- Env: `FX_ENABLED` (**default false** — tests and offline runs make no outbound
  request), `FX_PROVIDER_URL`, `FX_HTTP_TIMEOUT_SECONDS`.
- **Changing a company's base currency does not rewrite history inline.** Rows
  are rewritten by `POST /companies/{id}/recompute-fx` (management) or
  `python -m web_api.fx.backfill [--company-id …]`, each row at its *own*
  historical rate. In between, reports show two `base_currency` rows — visibly
  stale, not silently wrong.

## ERP entries

- `ErpEntry` is the atomic financial record (raw GL posting), never categorized.
  Its ledger date is `accounting_date` (the posting date; the axis for period
  reporting). It carries **no** direct `erp_integration_id` — the integration is
  reached through its account (`erp_account_id → ErpAccount.erp_integration_id`);
  `company_id` gives tenant scope. The sync scopes an integration's entries by
  joining through `ErpAccount`.
- `ErpEntry.source_invoice_line_id` links a posting to the **invoice line** it
  was posted from — **many entries → one line**, since a line can be posted
  across several accounts. Nullable, and null is the ordinary case: input VAT,
  the payable, journal entries and payments belong to a whole voucher, not a
  line. It is set only when the connector states the line
  (`ErpEntryData.source_line_erp_id`) and is **derived**, never matched — the
  runner rebuilds the line id from the same `(invoice, line_erp_id)` pair
  `_persist_invoices` used, so the two agree by construction; a reference to a
  line the scan never delivered is stored as null rather than aborting the sync.
  The entry is still never categorized: the category lives on the line and is
  only *read through* this link.
- `ErpEntryRead` **resolves the account and the supplier server-side**
  (`erp_account_code`/`erp_account_name`, `vendor_id`/`vendor_name`) — an entry
  carries only foreign keys, and the vendor is not even one of them (it is
  reached via `source_invoice_id → Invoice.vendor_id`), so a client would
  otherwise need three lookups per row. It also carries
  `source_invoice_line_id` and `spend_category_level_1/2/3`, read off the linked
  line — all null when there is no line, and the levels also null when the line
  is not categorized yet (the two are deliberately indistinguishable). `web_api/routers/erp_entries.py` builds
  every entry payload through one `_entry_select()`/`_entry_read()` pair and
  every filter through one `_entry_conditions()`, so the flat list, the voucher
  groups, and the detail endpoint cannot drift apart.

## Sync pipeline

- **The runner reads its work from the database, never from arguments.**
  `run_sync()` takes no tenant and no credentials: it syncs every
  `ErpIntegration` with `disconnected_at IS NULL`, taking `company_id` and
  `erp_type` off the row and decrypting that integration's own `ErpCredential`
  for the connector config. No credential row means the connector's declared
  field defaults — the normal case for the Debug ERP.
- **The runner never creates an Organization, Company, or ErpIntegration.**
  Those come from the frontend (`POST /companies` with its `integration` block).
  A company created in Settings is picked up by the next run with no code or
  flag change. Consequence: a cold database syncs nothing, by design.
- **Failures are isolated per integration.** An unreachable ERP or an
  undecryptable credential is recorded on that integration's `SyncState` and the
  run continues; the process exits non-zero if any integration failed.
- **Each integration syncs from its own watermark** (`SyncState.last_invoice_date`).
  `--since` overrides it for a backfill; a failed run never advances it.
- CLI: `--integration-id` (re-run one; it only *filters* the discovered set and
  can never create anything) and `--since`. There is no `--reset` — dropping the
  schema would delete the integrations that define the work list.
- The runner needs `WEB_API_CREDENTIAL_ENC_KEY` whenever an integration has
  stored credentials, since it decrypts them.

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
│   ├── fx/                   historical FX: rate provider + cache, convert,
│   │                         recompute, backfill CLI
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
    ├── sync/runner.py        pipeline orchestrator (discover→connect→fetch→persist→categorize)
    ├── sync/categorizer.py   deterministic keyword categorizer (stub for Qdrant+LLM)
    ├── aggregation/engine.py SQL rollups (stub)
    ├── redundancy/detector.py vendor overlap detection (stub)
    └── procurement_agent/recommender.py  savings suggestions (stub)

mock_erp/                     standalone mock ERP API server (unchanged)
```
