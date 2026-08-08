## Why

The admin panel can currently only *read*: the dashboard renders reports and the
sidebar's **Settings** item is a disabled stub. Everything a customer needs to
administer their own workspace — renaming the organization, inviting a colleague,
adding the second legal entity whose ERP data they want ingested — is only doable
from the Clerk dashboard or by hand in the database. The web API already exposes
the org profile and full company management, and Clerk already owns identity and
membership; nothing is missing but the UI in front of them.

This is also the app's first *write* surface. Everything after it — invoice
verification, ERP integration setup, category corrections — needs a mutating API
client, form-submit conventions, optimistic-vs-refetch rules, toast feedback, and
role-gated controls. Building those once, here, sets the pattern.

## What Changes

- **New `/settings` route** under the authenticated layout, organised as three
  tabs — **Profile**, **Organization**, **Companies** — with the active tab
  reflected in the URL (`/settings/profile`, `/settings/organization`,
  `/settings/companies`) so it is linkable and survives reload.

- **Profile (personal) settings**, built as custom forms on Clerk's client SDK
  in the house style — consistent with the existing custom sign-in screen, which
  deliberately avoids Clerk's prebuilt widget:
  - Name and avatar edit (`user.update()`, `user.setProfileImage()`).
  - Email addresses: list, add with verification-code confirmation, set primary,
    remove.
  - Password: change (and set, for OAuth-only accounts).
  - Active sessions: list other devices and revoke them.
  - Connected accounts: list OAuth providers, connect and disconnect.
  - App preferences: theme (light / dark / system), persisted as today.

- **Organization settings**:
  - Profile — name and slug via `PATCH /api/v1/organization`, plus the org logo
    via Clerk. Read-only status and creation date. Admin-only (system admin or
    org `admin`); other roles see the same panel disabled.
  - **Members** — full management through Clerk's `useOrganization`: the member
    list with role, invitations (invite by email with a role, list pending, and
    revoke), role changes, and removal. Clerk is the source of truth for
    membership; the existing Clerk webhook keeps `User.role` in sync locally, so
    no bespoke membership API is introduced. Self-demotion and removing the last
    admin are blocked in the UI.
  - **Danger zone** — suspend the organization via `DELETE /api/v1/organization`
    (a soft-suspend that retains all data and propagates to Clerk), behind a
    typed-name confirmation and visible to admins only.

- **Companies settings** — the full existing management surface: list (including
  inactive), create, edit name / country / VAT, and deactivate / reactivate,
  against `GET|POST /api/v1/companies`, `PATCH /api/v1/companies/{id}`, and
  `POST /api/v1/companies/{id}/deactivate|activate`. Write controls are gated on
  `require_management`'s rule (system admin, `admin`, or `moderator`);
  `member` / `viewer` get a read-only table. ERP integration setup is explicitly
  **out of scope** for this change.

- **The API client learns to write.** `createApiClient` gains `post`, `patch`,
  and `del` with JSON bodies, keeping the existing `ApiError` contract, and
  gaining structured extraction of FastAPI's `detail` so a 403 or a 409 renders
  as a real message instead of "Request failed with 409".

- **The app shell becomes shared.** The sidebar / topbar shell currently lives
  inside the dashboard route component; it moves into the `_authed` layout (or a
  shared component it renders) so `/settings` and every later page inherit it.
  Sidebar items become real router `<Link>`s with active state driven by the
  router, and **Settings** stops being disabled.

- **No backend changes.** Every capability above is served by an endpoint that
  already exists or by Clerk. This was verified endpoint by endpoint while
  scoping; if implementation uncovers a genuine gap, it is a follow-up change
  rather than a silent widening of this one.

## Capabilities

### New Capabilities

- `frontend-settings`: the settings area — its route/tab structure, the personal
  profile and security panels backed by Clerk, organization profile and member
  management, company management, role-based gating of every write control, and
  the save / error / feedback behaviour shared by its forms.

### Modified Capabilities

- `frontend-ui-library`: the theming requirement extends from light/dark to a
  stored *preference* of light, dark, or **system** — the provider resolves the
  applied theme from the OS when `system` is chosen, and exposes the preference
  alongside the resolved theme so the settings control can reflect the actual
  choice. (Added during implementation, once the settings area needed a theme
  control offering more than a two-way toggle.)

- `frontend-auth-dashboard`: the "Authenticated API access to the web API"
  requirement extends from a read-only client to one that also performs
  authenticated writes (POST / PATCH / DELETE with JSON bodies) and surfaces the
  API's error detail; and a new requirement covers the persistent application
  shell — navigation shared across all authenticated routes, with the active
  route highlighted — which the dashboard route previously owned privately.

## Impact

- **Code (frontend)**: `src/routes/_authed/settings.tsx` and its child routes
  (new); `src/components/settings/*` (new — profile, security, organization,
  members, companies panels); `src/components/app-shell.tsx` or `_authed.tsx`
  (shell extraction); `src/routes/_authed/index.tsx` (shell removal);
  `src/lib/api-client.ts` (mutation verbs, error detail); `src/lib/types.ts`
  (`OrganizationRead`, `CompanyRead`, and the update payload types);
  `src/lib/organization.ts`, `src/lib/companies.ts` (new query/mutation
  options); `src/routeTree.gen.ts` (regenerated).
- **Backend**: none. `web_api` endpoints and Clerk are consumed as they are.
- **Dependencies**: none added. Tabs, Form, Input, Switch, Select, AlertDialog,
  DataTable, Avatar, Badge, and Toast all already exist in the UI library.
- **Related in-flight work**: `frontend-org-switcher` also touches `_authed.tsx`
  and the sidebar header. Whichever lands second rebases on the other; the
  overlap is the shell, and this change deliberately does not introduce a second
  org-selection surface.
- **Risk**: two sources of truth for identity — Clerk (authoritative for users,
  membership, roles) and the local `User`/`Organization` rows (populated by
  webhook and JIT provisioning). A member invited in the UI has no local row
  until they first sign in, and a role change lands locally only once the webhook
  is processed. The settings UI therefore reads membership from Clerk and the org
  profile from the web API, and refetches `GET /users/me` after any change that
  can alter the caller's own role or org.
