## Why

The categorization pipeline lands raw ERP data (invoices + lines) in PostgreSQL, but there is no way for a customer to see it. Enterprise customers need to sign in and review the raw, uncategorized data that was pulled from their ERP before trusting the automated categorization. We need a backend API — the foundation the future frontend will call — that authenticates real users and serves their company's data, safely scoped so no tenant can ever see another's rows.

## What Changes

- Add a new FastAPI application module `src/web_api/` (served by uvicorn, following the existing `mock_erp/` patterns) that will back the enterprise frontend.
- Authenticate requests with **Clerk** (hosted auth). The API does **not** implement signup/login or store passwords — it verifies Clerk-issued session JWTs (`Authorization: Bearer`) against Clerk's JWKS.
- **Just-in-time provisioning**: on the first authenticated request, map the caller's Clerk organization → our `Organization` and Clerk user → our `User`, persisting the Clerk IDs. Clerk org role maps to `User.role` (`admin`/`member`/`viewer`).
- Enforce multi-tenant scoping in a shared FastAPI dependency: every data query is filtered to the caller's `organization_id` / accessible `company_id`s.
- Add read-only endpoints for reviewing raw/uncategorized data (the first frontend surface):
  - list the caller's companies
  - list invoices (filter by status, paginated) and fetch one invoice with its lines
  - list invoice lines (filter by status/company, paginated)
- **BREAKING** (schema): add `clerk_user_id` to `User` and `clerk_org_id` to `Organization` (nullable, unique) plus an Alembic migration.
- `ErpEntry` (raw double-entry GL rows) is explicitly **out of scope** here — no pipeline populates it yet; the review surface uses `Invoice`/`InvoiceLine` with `status = pending`.

## Capabilities

### New Capabilities
- `web-api-auth`: Clerk JWT verification, just-in-time `Organization`/`User` provisioning, and the tenant-scoping request dependency that all data endpoints depend on.
- `web-api-invoice-review`: read-only, org-scoped HTTP endpoints for listing companies, invoices, and invoice lines (including raw uncategorized/pending rows) with filtering and pagination.

### Modified Capabilities
- `domain-model`: `User` and `Organization` gain external-identity fields (`clerk_user_id`, `clerk_org_id`) so app records can be linked to Clerk principals.

## Impact

- **New module**: `src/web_api/` (app factory, Clerk auth dependency, routers, Pydantic response schemas), plus `tests/web_api/`.
- **Schema/ORM**: `User`, `Organization` columns + Alembic migration.
- **Dependencies**: add `pyjwt[crypto]` for RS256 JWKS verification (httpx already present for JWKS fetch). Optional Clerk backend SDK not required.
- **Config**: new env vars — `CLERK_ISSUER`, `CLERK_JWKS_URL`, `CLERK_AUDIENCE` (and a test/dev bypass toggle).
- **Testability**: the Clerk verifier is injected so tests use a fake verifier and an in-memory/SQLite DB — no live Clerk or Postgres required.
- **Run**: `uvicorn web_api.app:app` (new); does not affect the sync runner, PDF flow, or Streamlit dashboard.
