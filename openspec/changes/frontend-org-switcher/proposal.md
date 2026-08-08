## Why

A user can belong to several organizations, but the app activates the *first*
membership it finds and offers no way to change it — so anyone with more than one
org is stuck looking at whichever tenant Clerk happened to return first. Because
the web API derives tenant scope from the `orgId` claim in the Clerk session
token, switching organizations is the only way to see another tenant's data.

At the same time the UI library has no searchable, type-to-filter select. The org
switcher needs one, and so will vendor pickers, company filters, and category
pickers on the pages that follow — so the primitive should be built once, in the
library, rather than inlined into the switcher.

## What Changes

- **New `Combobox` primitive** in `frontend/src/components/ui/`, built on Base UI's
  headless `combobox` (already present in `@base-ui-components/react@1.0.0-rc.0`)
  and styled with the ERPSAA tokens like the rest of the library. Generic over the
  item type, with text filtering, keyboard navigation, controlled/uncontrolled
  value, empty state, loading state, optional grouping, and a `render`-able trigger
  so callers can style it as a workspace switcher, a form field, or a toolbar
  filter. Exported from the `#/components/ui` barrel and added to the `/ui`
  kitchen-sink route.
- **New `OrgSwitcher` component** consuming that primitive: lists the signed-in
  user's Clerk organization memberships, shows the active one, filters by name,
  and activates the chosen org via Clerk's `setActive`.
- **Switching resets tenant-scoped state**: on a successful switch the TanStack
  Query cache is cleared/invalidated so no data from the previous organization is
  shown, and `GET /users/me` is refetched so the principal (role, organization id)
  matches the new tenant.
- **Placement in the app shell**: the switcher sits in the sidebar header next to
  the product mark, visible on every authenticated page. With a single membership
  it renders as a static, non-interactive label rather than an empty picker.
- **Membership loading is centralized**: `_authed.tsx` already reads
  `useOrganizationList` to resolve the pending-org task; that logic and the
  switcher share one source of memberships instead of two independent listings.

No API changes: tenant scope already follows the Clerk token, and
`GET /users/me` already JIT-provisions the principal for the active org.

## Capabilities

### New Capabilities

_None._ Both changes extend existing frontend capabilities.

### Modified Capabilities

- `frontend-ui-library`: adds a searchable **Combobox** primitive to the required
  component set — a new requirement covering its filtering, keyboard, and state
  behaviour, plus its inclusion in the single import surface and the kitchen-sink
  route.
- `frontend-auth-dashboard`: adds an **organization switcher** requirement — the
  active organization is displayed and changeable from the app shell, and
  switching re-scopes the session, the principal, and all cached tenant data.

## Impact

- **Code**: `frontend/src/components/ui/combobox.tsx` (new),
  `frontend/src/components/ui/index.ts`, `frontend/src/components/ui/ui.test.tsx`,
  `frontend/src/routes/ui.tsx`, `frontend/src/components/org-switcher.tsx` (new),
  `frontend/src/routes/_authed.tsx`, `frontend/src/routes/_authed/index.tsx`
  (shell wiring), `frontend/src/lib/auth.tsx` (principal refresh on switch).
- **Dependencies**: none added — Base UI's `combobox` ships in the installed
  version.
- **Backend**: unaffected. Tenant scoping, org suspension checks, and JIT
  provisioning in `web_api` already key off the token's `orgId`.
- **Risk**: stale cross-tenant data if the query cache is not reset on switch —
  addressed explicitly by the reset requirement and a test.
