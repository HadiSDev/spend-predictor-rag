## Context

The sync runner persists `Invoice`/`InvoiceLine` rows (status `pending` until categorized) into PostgreSQL, scoped by `company_id` under an `Organization → Company` hierarchy. There is no external interface to that data. We are adding the first HTTP surface — a FastAPI app that the future enterprise frontend will call — starting with authentication and read-only review of the raw/uncategorized data.

Auth is delegated to **Clerk**: the frontend uses Clerk for signup/login and sends Clerk session JWTs to our API. Our API is a resource server — it verifies tokens and serves tenant-scoped data. The repo already ships a FastAPI service (`mock_erp/`) whose structure (app object, routers, pagination envelope, header auth middleware) is the reference pattern.

Constraints: Python 3.12, SQLModel over the existing `db/session.py` engine, reuse existing ORM models, no live Clerk or Postgres required to run the test suite.

## Goals / Non-Goals

**Goals:**
- A runnable FastAPI app (`web_api.app:app`) with Clerk bearer auth.
- Idempotent JIT provisioning of `Organization`/`User` from Clerk principals.
- A single tenant-scoping dependency every data route depends on.
- Read-only endpoints: companies, invoices (list + detail with lines), invoice lines — with `status`/`company_id` filters and pagination.
- Fully unit-testable via an injected verifier + SQLite, deterministic ordering.

**Non-Goals:**
- No signup/login/password logic (Clerk owns it).
- No writes/mutations beyond provisioning (dismiss, re-categorize, upload come later).
- `ErpEntry` GL rows (no pipeline populates them yet).
- Webhook-based Clerk sync, RBAC enforcement beyond role mapping, rate limiting.

## Decisions

### Verify Clerk JWTs locally with `pyjwt[crypto]` + a cached JWKS client
Clerk signs session tokens with RS256; public keys are published at the instance JWKS URL. We fetch the JWKS (httpx), cache keys by `kid`, and verify signature + `iss` + `exp`/`nbf` (and `aud` when `CLERK_AUDIENCE` is set). Alternative — the Clerk backend SDK or a `/v1/sessions/verify` network call per request — was rejected: local JWKS verification is stateless, fast, and needs no extra service dependency. Tenant/role claims (`org_id`, `org_role`, and `sub` for the user) are read from the verified payload; exact claim names are configurable to track Clerk token shape.

### Auth as a FastAPI dependency chain, not middleware
`verify_token` (returns a `ClerkPrincipal`) → `current_user` (provisions/loads `User`, opens a session) → `tenant_scope` (returns `organization_id` + accessible `company_id`s). Routes declare `Depends(tenant_scope)`. The verifier is provided via `app.dependency_overrides`-friendly injection so tests swap in a fake. This keeps `401` handling and scoping centralized and composable.

### JIT provisioning is find-or-create keyed by Clerk IDs
`Organization` by `clerk_org_id`, `User` by `clerk_user_id`. On each request we upsert mutable fields (name/email/role); unknown Clerk roles fall back to `viewer`. Provisioning runs in the request transaction and is safe under the unique constraints (`clerk_org_id`, `clerk_user_id`).

### Response models are explicit Pydantic schemas, not raw ORM objects
Routers return `CompanyRead`, `InvoiceRead`, `InvoiceLineRead`, and a generic `Page[T]` envelope (`items`, `page`, `page_size`, `total`) mirroring `mock_erp`'s pagination. This decouples the wire contract from the schema, avoids leaking internal columns, and keeps serialization predictable.

### Tenant scoping enforced in SQL, never trusting client tenant input
Every query joins/filters through `Company.organization_id == scope.organization_id`. A client-supplied `company_id` is validated against the scope; a non-member id yields `404`. There is no code path where a tenant identifier from the request widens access.

### Schema change via nullable unique columns + Alembic migration
Add `Organization.clerk_org_id` and `User.clerk_user_id` (nullable, unique). Nullable keeps synthetic/demo tenants (created by the sync runner without Clerk) valid. One Alembic migration adds the columns and unique indexes.

## Risks / Trade-offs

- **Clerk token claim shape drifts** (e.g. org claims only present with an active org, or v2 `o` claim) → make claim names configurable and treat "no org claim" as an explicit `401`/`403` with a clear message; cover with tests using representative payloads.
- **JWKS fetch failure or key rotation** → cache keys, refresh on unknown `kid`, and fail closed (`401`) rather than accepting unverified tokens.
- **Provisioning race on first concurrent requests** → rely on the DB unique constraint; catch the integrity error and re-read the existing row.
- **Read models drift from ORM** → response schemas are small and covered by endpoint tests asserting field presence.
- **Multi-tenant leak** → the single scoping dependency plus explicit cross-tenant tests (`404` on foreign `company_id`/`invoice_id`) are the guardrail; no route queries without it.

## Migration Plan

1. Add `pyjwt[crypto]` dependency; add `CLERK_ISSUER`, `CLERK_JWKS_URL`, `CLERK_AUDIENCE` (+ optional `WEB_API_AUTH_DISABLED` dev toggle) to config and `.env.example`.
2. Add the two nullable-unique columns to the ORM models; generate + apply the Alembic migration.
3. Build the `web_api` module (app, auth deps, schemas, routers) and tests.
4. Run locally: `uvicorn web_api.app:app --reload`; verify with a real Clerk token manually, and the suite with a fake verifier.
Rollback: the module is additive and isolated; drop the router include and (if needed) revert the migration. No existing pipeline depends on it.

## Open Questions

- Exact Clerk claim names for org/role in this instance's token template — confirm against a real token during implementation (design keeps them configurable).
- Should users without an active Clerk organization be rejected (`403`) or provisioned into a personal org? Default: reject with a clear message until org-less access is needed.
