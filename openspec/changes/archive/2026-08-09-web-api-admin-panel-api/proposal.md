## Why

The API already covers the admin panel's core screens (companies, invoices/line
review + verify, ERP entries, integrations, reports). Three gaps block actually
shipping a browser front-end for the **enterprise org admin**: the browser can't
call the API (no CORS), the panel can't tell who is logged in or their role, and
there is no team/members view. This change closes those blockers plus the cheap
"my vendors" read the spend screens need.

## What Changes

- **CORS** — add configurable CORS middleware so a browser SPA on the panel's
  origin can call the API. Allowed origins come from `WEB_API_CORS_ORIGINS`
  (comma-separated); empty by default (no cross-origin) so prod is opt-in.
- **Current user** — `GET /api/v1/users/me` returns the authenticated user
  (id, email, name, org role, `is_system_admin`, organization) so the front-end
  can render role-aware UI.
- **Member directory** — `GET /api/v1/users` lists the caller's organization
  members (read-only; roles are still managed in Clerk). Tenant-scoped.
- **Vendor list** — `GET /api/v1/vendors` returns the vendors the caller's org
  actually transacts with (distinct vendors on the org's invoices), with an
  optional `q` name/VAT search and pagination. Not the whole global catalog, to
  avoid leaking other tenants' suppliers.
- All new endpoints are read-only, reuse the existing `tenant_scope` chain, and
  need no DB migration.

## Capabilities

### New Capabilities
- `web-api-admin-panel`: the API surface a browser admin panel needs beyond the
  existing endpoints — cross-origin (CORS) access, a current-user endpoint, an
  organization member directory, and a tenant-scoped vendor list.

### Modified Capabilities

## Impact

- `web_api/config.py` (`WEB_API_CORS_ORIGINS`), `web_api/app.py` (CORS
  middleware + new routers), new `web_api/routers/users.py` and
  `web_api/routers/vendors.py`, new response schemas in `web_api/schemas.py`.
- Reuses `deps.tenant_scope` / `current_user`; no new auth model, no migration.
- **Deferred (not in this change):** spend-tree read (`GET /spend-categories`),
  ERP sync-status read, and any "sync now" trigger — add when the panel screens
  that need them are built.
- Docs: `CLAUDE.md` endpoint list + `.env.example` (`WEB_API_CORS_ORIGINS`).
