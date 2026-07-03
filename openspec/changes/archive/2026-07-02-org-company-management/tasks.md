## 1. Schema & migration

- [x] 1.1 Add `slug` (nullable, unique) and `status` (default `active`) to the `Organization` ORM model
- [x] 1.2 Add `is_active` (default `true`) and `deactivated_at` (nullable) to the `Company` ORM model
- [x] 1.3 Add `is_system_admin` (default `false`) to the `User` ORM model
- [x] 1.4 Create one Alembic migration for all three tables (+ unique index on `organizations.slug`); apply it to the dev DB
- [x] 1.5 Confirm the sync runner still provisions synthetic tenants (defaults applied, no regression)

## 2. Config

- [x] 2.1 Add `CLERK_SYSTEM_ADMIN_CLAIM` to `web_api/config.py` and `.env.example` (claim name that marks a system admin)

## 3. Authorization layer (web-api-authorization)

- [x] 3.1 Extend the Clerk principal / provisioning to map the `moderator` org role (unknown still → `viewer`)
- [x] 3.2 Provision `User.is_system_admin` from the configured Clerk claim (absent/false → not admin); refresh on each request
- [x] 3.3 Add a `require_management` dependency: allow iff `is_system_admin` or role in {`admin`,`moderator`}, else `403`
- [x] 3.4 Add a stricter `require_org_admin` dependency (system admin or `admin`) for org-profile updates
- [x] 3.5 Ensure non–system-admin callers stay confined to their own organization; system admins may target any org

## 4. Write schemas

- [x] 4.1 Add `CompanyCreate` (name required; country_code/vat_number optional; optional `organization_id` for system admins) and `CompanyUpdate`
- [x] 4.2 Add `OrganizationRead` and `OrganizationUpdate` (name, slug)
- [x] 4.3 Extend `CompanyRead` to expose `is_active`

## 5. Company management endpoints (web-api-company-management)

- [x] 5.1 `POST /api/v1/companies` — create under caller's org (or target org for system admin); `201`; `require_management`
- [x] 5.2 `PATCH /api/v1/companies/{id}` — update name/country_code/vat_number; `404` if out of scope; `require_management`
- [x] 5.3 `POST /api/v1/companies/{id}/deactivate` — set `is_active=false` + `deactivated_at`; `require_management`
- [x] 5.4 `POST /api/v1/companies/{id}/activate` — set `is_active=true`, clear `deactivated_at`; `require_management`
- [x] 5.5 Update `GET /api/v1/companies` to exclude inactive by default with `include_inactive=true` opt-in
- [x] 5.6 Wire the router into the app factory

## 6. Organization endpoints (web-api-org-management)

- [x] 6.1 `GET /api/v1/organization` — caller's org profile (any authenticated member)
- [x] 6.2 `PATCH /api/v1/organization` — update name/slug; `require_org_admin`; `409` on duplicate slug
- [x] 6.3 Wire the router into the app factory

## 7. Tests

- [x] 7.1 Fixtures: extend seed with users across roles (system admin, admin, moderator, member, viewer) via fake-verifier tokens
- [x] 7.2 Authorization matrix: writes allowed for system admin/admin/moderator, `403` for member/viewer
- [x] 7.3 Company create (201 + `422` on missing name), update, deactivate/activate; list hides inactive unless `include_inactive=true`
- [x] 7.4 Cross-tenant: foreign company id → `404`; cross-org create/update by a system admin succeeds
- [x] 7.5 Org profile: read returns own org; update by admin ok, by moderator `403`, duplicate slug `409`
- [x] 7.6 Provisioning: `moderator` mapped; `is_system_admin` set from claim / absent
- [x] 7.7 Run `uv run pytest` — full suite green

## 8. Docs

- [x] 8.1 Update `CLAUDE.md` (new endpoints + role model + `CLERK_SYSTEM_ADMIN_CLAIM`)
