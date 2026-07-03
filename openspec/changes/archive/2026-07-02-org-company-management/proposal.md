## Why

Clerk creates users and organizations, and our API just-in-time provisions a thin `Organization` mirror on first request — but there is no way for a customer to actually onboard: create the companies whose spend they want analyzed, or manage their organization's profile. The `Organization` today is a bare Clerk mirror (`id`, `name`, `clerk_org_id`); we need it to be a real domain entity, and we need write endpoints so an organization's admins can stand up one or more companies under it.

## What Changes

- Keep Clerk as the identity/org source (JIT provisioning stays); **enrich the `Organization` domain model** with profile/lifecycle fields and expose read/update of the org profile.
- Add **company management** endpoints so an organization can create and maintain the companies under it:
  - `POST /api/v1/companies` — create a company under the caller's organization
  - `PATCH /api/v1/companies/{id}` — update name / country_code / vat_number
  - `POST /api/v1/companies/{id}/deactivate` and `.../activate` — soft deactivate / reactivate (no hard delete — companies own financial data)
  - the existing companies list excludes deactivated companies by default (`include_inactive=true` to include)
- Add a **role-based write-authorization** layer:
  - introduce a platform-level **system admin** (`User.is_system_admin`) who can manage any organization
  - introduce an org **`moderator`** role alongside `admin`; write operations require system admin **or** org `admin`/`moderator`; `member`/`viewer` are read-only
- Add **organization profile** endpoints:
  - `GET /api/v1/organization` — the caller's organization profile
  - `PATCH /api/v1/organization` — update org profile (system admin or org admin)

## Capabilities

### New Capabilities
- `web-api-authorization`: the platform/organization role model (system admin + `admin`/`moderator`/`member`/`viewer`), how those are provisioned from Clerk claims, and the shared write-authorization dependency that management endpoints use.
- `web-api-company-management`: create, update, and (de)activate companies under an organization, org-scoped and role-gated, plus active-state filtering on the companies list.
- `web-api-org-management`: read and update the caller's organization profile.

### Modified Capabilities
- `domain-model`: `Organization` gains profile/lifecycle fields (`slug`, `status`); `Company` gains soft-deactivation fields (`is_active`, `deactivated_at`); `User` gains `is_system_admin` and the role set gains `moderator`.

## Impact

- **Schema/ORM**: new columns on `organizations` (`slug`, `status`), `companies` (`is_active`, `deactivated_at`), `users` (`is_system_admin`); one Alembic migration. All nullable/defaulted so existing rows and synthetic tenants stay valid.
- **Code** (`src/web_api/`): new `routers/` for company writes and organization profile; a `require_management` authorization dependency in `deps.py`; role/system-admin provisioning extended in `auth.py`/`deps.py`; request (write) Pydantic schemas in `schemas.py`.
- **Config**: optional `CLERK_SYSTEM_ADMIN_CLAIM` to name the Clerk claim that marks a system admin.
- **Tests**: `tests/web_api/` — company create/update/(de)activate, org profile read/update, authorization matrix (system admin / admin / moderator / member / viewer), cross-tenant isolation.
- Read endpoints, the sync runner, PDF flow, and Streamlit dashboard are unaffected.
