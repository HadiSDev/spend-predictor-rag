## Context

The Clerk-auth web API (`src/web_api/`) verifies tokens, JIT-provisions a thin `Organization`/`User`, scopes reads to the caller's org, and serves read-only invoice/company data. There is no onboarding: no way to create the companies whose spend is analyzed, and the `Organization` is a bare Clerk mirror. This change adds the write side — company management and org-profile management — plus the role model those writes need. Clerk remains the identity/org source; provisioning stays JIT.

## Goals / Non-Goals

**Goals:**
- Make `Organization` a real domain entity (profile + lifecycle) with read/update endpoints.
- Company create / update / soft-deactivate / reactivate under an organization.
- A role model — platform system admin + org `admin`/`moderator`/`member`/`viewer` — with a single reusable write-authorization dependency.
- Everything unit-testable with the injected fake verifier + SQLite (as the existing web_api tests).

**Non-Goals:**
- No org creation *in our API* (Clerk still creates orgs; JIT still mirrors them). The "no Clerk org → 403" behavior is unchanged.
- No hard delete of companies (they own financial data).
- No Clerk webhooks, no per-company roles, no billing/plan modeling, no user-management endpoints.

## Decisions

### Keep Clerk/JIT for orgs; enrich the Organization entity, don't create orgs
Organizations continue to be provisioned from the Clerk org on first request. This change adds domain fields (`slug`, `status`) and a profile endpoint, so "we need a domain model for organizations" is satisfied without introducing an API-driven org-creation path (which would duplicate Clerk's org lifecycle and reopen the 403 question). Alternative considered — an API `POST /onboarding` that creates the org — was rejected for now to keep one source of truth for org identity.

### One authorization dependency, layered on the existing auth chain
Add `require_management` after `current_user`/`tenant_scope`: it permits the request iff `user.is_system_admin` or `user.role in {admin, moderator}`, else `403`. Management routers depend on it; read routers keep using `tenant_scope` only. Org-profile *update* uses a stricter `require_org_admin` (system admin or `admin`; not `moderator`). Centralizing the checks keeps `403` semantics in one place and avoids per-route role logic. The role enum lives with the domain (`admin`/`moderator`/`member`/`viewer`); the mapping adds `moderator` and still defaults unknown → `viewer`.

### System admin is a platform flag provisioned from a configurable Clerk claim
`User.is_system_admin` (bool) is set during provisioning from `CLERK_SYSTEM_ADMIN_CLAIM` (a claim name, default e.g. `system_admin`); absent/false → not a system admin. System admins bypass the org-role check and the single-org confinement, so they can manage any organization (targeting one via an explicit `organization_id` on create, or by id lookup on update). Regular admins/moderators are confined to their own org by tenant scope. Alternative — a separate super-admin table/allowlist — was rejected as heavier; the claim keeps identity in Clerk.

### Soft deactivation, never hard delete
`Company` gains `is_active` (default true) + `deactivated_at`. `deactivate`/`activate` are explicit POST actions (not PATCH of a client-set flag) so the state transition is unambiguous and auditable. The companies list filters to active by default (`include_inactive=true` to include). Invoices/lines are untouched, preserving history and FKs.

### Explicit write schemas; reuse existing read schemas
Add `CompanyCreate`, `CompanyUpdate`, `OrganizationRead`, `OrganizationUpdate` Pydantic models (request bodies validated, unknown fields rejected). Responses reuse/extend `CompanyRead` (now including `is_active`) and a new `OrganizationRead`. This keeps the wire contract explicit and decoupled from the ORM.

### Schema change via nullable/defaulted columns + one Alembic migration
`organizations` += `slug` (nullable, unique), `status` (default `active`); `companies` += `is_active` (default true), `deactivated_at` (nullable); `users` += `is_system_admin` (default false). All additive and backfill-safe, so existing rows and synthetic tenants remain valid. One migration, mirroring `0001`.

## Risks / Trade-offs

- **System-admin claim shape unknown** → make the claim name configurable and treat missing/false as not-admin (fail safe); cover with tests using representative payloads.
- **Cross-org system-admin widens blast radius** → the default path is still org-scoped; system-admin cross-org actions require an explicit target id and are covered by dedicated tests. Keep the surface small (companies + org profile only).
- **`slug` uniqueness collisions** on update → return `409 Conflict`, catch the integrity error, and make no change.
- **Role drift vs the unarchived `web-api-auth` capability** → the extra role/flag provisioning is specified here as `web-api-authorization` (additive) rather than modifying the not-yet-archived `web-api-auth`, so specs compose cleanly at archive time.
- **List behavior change** (active-only default) could hide data from existing callers → documented, opt-in `include_inactive`, and asserted in tests.

## Migration Plan

1. Add columns to `Organization`, `Company`, `User` ORM models; generate + apply one Alembic migration.
2. Extend provisioning (`deps.py`/`auth.py`) to map `moderator` and set `is_system_admin` from `CLERK_SYSTEM_ADMIN_CLAIM`; add `require_management` / `require_org_admin` dependencies.
3. Add write schemas and the company-management + organization routers; filter the companies list by active state.
4. Tests: authorization matrix, company create/update/(de)activate, org read/update, cross-tenant + cross-org (system admin) cases. Run `uv run pytest`.
Rollback: endpoints are additive; drop the new routers/deps and revert the migration. Reads and pipelines are unaffected.

## Open Questions

- Exact Clerk claim carrying system-admin status (kept configurable via `CLERK_SYSTEM_ADMIN_CLAIM`; confirm against a real token).
- Should `member` retain any write capability later? For now `member` is read-only for management (only `admin`/`moderator`/system admin write).
