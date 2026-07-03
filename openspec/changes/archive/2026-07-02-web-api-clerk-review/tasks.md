## 1. Dependencies & config

- [x] 1.1 Add `pyjwt[crypto]` to `pyproject.toml` dependencies and run `uv sync`
- [x] 1.2 Add Clerk settings to `config.py`: `CLERK_ISSUER`, `CLERK_JWKS_URL`, `CLERK_AUDIENCE`, and a `WEB_API_AUTH_DISABLED` dev/test toggle (all via env with sane defaults)
- [x] 1.3 Document the new env vars in `.env.example`

## 2. Schema change (external identity)

- [x] 2.1 Add nullable, unique `clerk_org_id` to `Organization` ORM model
- [x] 2.2 Add nullable, unique `clerk_user_id` to `User` ORM model
- [x] 2.3 Create an Alembic migration adding both columns + unique indexes; apply it against the dev DB
- [x] 2.4 Confirm the sync runner still provisions synthetic `Organization`/`User` with NULL Clerk IDs (no regression)

## 3. Clerk auth (web-api-auth capability)

- [x] 3.1 Create `web_api/` package skeleton: `app.py` (app factory), `deps.py`, `schemas.py`, `routers/`
- [x] 3.2 Implement a JWKS client that fetches keys via httpx, caches by `kid`, and refreshes on unknown `kid`
- [x] 3.3 Implement `verify_token` returning a `ClerkPrincipal` (user id, org id, role, name/email); validate signature, `iss`, `exp`/`nbf`, and `aud` when configured; make the verifier injectable/overridable for tests
- [x] 3.4 Implement `current_user` dependency: idempotent find-or-create of `Organization` (by `clerk_org_id`) and `User` (by `clerk_user_id`), mapping Clerk role → `admin`/`member`/`viewer` (unknown → `viewer`), updating mutable fields, handling the unique-constraint race
- [x] 3.5 Implement `tenant_scope` dependency returning `organization_id` + accessible `company_id`s, sourced only from the principal
- [x] 3.6 Return `401` for missing/malformed/invalid tokens with a generic message (no leak of which check failed)

## 4. Read endpoints (web-api-invoice-review capability)

- [x] 4.1 Define Pydantic read schemas: `CompanyRead`, `InvoiceRead`, `InvoiceLineRead`, and generic `Page[T]` envelope (`items`, `page`, `page_size`, `total`)
- [x] 4.2 `GET /api/v1/companies` — list the caller's organization's companies
- [x] 4.3 `GET /api/v1/invoices` — list invoices with `status` + `company_id` filters and pagination, deterministic ordering; validate `company_id` against scope (`404` if foreign)
- [x] 4.4 `GET /api/v1/invoices/{invoice_id}` — invoice header + its lines; `404` if not in caller's organization
- [x] 4.5 `GET /api/v1/invoice-lines` — list lines with `status` + `company_id` filters and pagination (primary review table)
- [x] 4.6 Add a `GET /api/v1/health` endpoint (unauthenticated) mirroring `mock_erp`
- [x] 4.7 Wire routers into the app factory and confirm `uvicorn web_api.app:app` boots

## 5. Tests

- [x] 5.1 Test fixtures: in-memory SQLite engine (monkeypatched), a fake Clerk verifier injected via `dependency_overrides`, and seed data (org A + org B with companies/invoices/lines)
- [x] 5.2 Auth tests: valid token passes; missing/malformed/invalid/expired token → `401`; unknown role → `viewer`
- [x] 5.3 Provisioning tests: first request creates `Organization`+`User`; repeat requests create no duplicates and update role/name/email
- [x] 5.4 Endpoint tests: companies/invoices/invoice-lines return only the caller's org data; `status`/`company_id` filters and pagination (`total`, `page_size`) work; ordering deterministic
- [x] 5.5 Cross-tenant tests: foreign `company_id`/`invoice_id` → `404`; org with no data → empty page, `total = 0`
- [x] 5.6 Run `uv run pytest` — full suite green

## 6. Docs

- [x] 6.1 Update `CLAUDE.md` (layout + run command for the web API) and note the Clerk env requirements
