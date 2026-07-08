## Context

The web API is a Clerk-authenticated resource server with a `tenant_scope`
dependency (yields the caller's `organization_id`, `role`, `company_ids`,
`is_system_admin`) and `current_user` (the provisioned `User`). Front-end work
is about to start; today a browser SPA can't call the API (no CORS), can't fetch
"who am I", can't list org members, and has no vendor read. `User` holds
`email`/`name`/`role`/`is_system_admin`/`organization_id`; `Vendor` is a global
catalog with only `Invoice.vendor_id` referencing it.

## Goals / Non-Goals

**Goals:**
- Unblock a browser admin panel: cross-origin access + a current-user endpoint.
- A read-only org member directory and a tenant-relevant vendor list.
- No new auth model, no migration; reuse the existing dependency chain.

**Non-Goals:**
- Managing members/roles from our API (roles stay in Clerk; this is read-only).
- Exposing the entire global vendor catalog across tenants.
- Spend-tree read, sync-status read, and "sync now" — deferred to later changes.
- Building the front-end itself.

## Decisions

### CORS is config-driven and opt-in
Add `CORSMiddleware` in the app factory with origins from
`WEB_API_CORS_ORIGINS` (comma-separated, trimmed). Empty ⇒ no cross-origin
allowed (prod is explicit); dev sets e.g. `http://localhost:5173`. Allow
credentials, standard methods/headers. This is the single browser-access
blocker and is cheap and reversible.

### `GET /users/me` — current principal
Returns the provisioned `User` for the bearer token via `current_user`:
`id`, `email`, `name`, `role`, `is_system_admin`, `organization_id`. The
front-end uses it to gate role-aware UI. No secrets (`clerk_user_id` omitted).

### `GET /users` — member directory, read-only, tenant-scoped
Lists `User` rows for the caller's `organization_id` (any authenticated org
member may read, consistent with the other read endpoints). Paginated envelope
like the other lists. Roles are **not** editable here — Clerk remains the source
of truth and the webhook keeps `User.role` in sync. System admins see their own
org by default; cross-org member listing is out of scope.

### `GET /vendors` — tenant-relevant, not the global table
Although `Vendor` is a global catalog, returning all rows would leak other
tenants' suppliers. The endpoint returns the **distinct vendors referenced by
the caller's invoices** (`Invoice.vendor_id` where `Invoice.company_id` is in
scope), with an optional `q` substring match on `name`/`vat_number` and
pagination. This matches what the panel needs ("our suppliers") and preserves
tenant isolation without changing the vendor's global identity.

### Read-only, dependency reuse
All endpoints depend on `tenant_scope`/`current_user`; none write, so there is
no migration and no new authorization gate. New routers `users.py` and
`vendors.py` follow the existing router style and are registered in `app.py`.

## Risks / Trade-offs

- **CORS misconfiguration** (e.g. accidental `*` with credentials) → mitigated by
  empty default and explicit env; document the dev value in `.env.example`.
- **Member directory exposure** — any org member can see the member list (names,
  emails, roles). Acceptable for a team view; tighten to management later if a
  tenant objects.
- **Vendor scoping via invoices** → a supplier with no invoice yet won't appear;
  correct for "our suppliers", and avoids a global-catalog leak. If a full
  catalog picker is later needed, add a separate explicitly-global endpoint.
- **No pagination cap surprises** → reuse the existing `Page` envelope and
  `page_size` bounds.
