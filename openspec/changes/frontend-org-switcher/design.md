## Context

The frontend is a TanStack Start app using Clerk (`@clerk/tanstack-react-start`)
for sessions and an in-house UI library over Base UI
(`@base-ui-components/react@1.0.0-rc.0`) for components. Tenant scope is not a
frontend concept: `web_api` reads the `orgId` claim from the Clerk session token
and scopes every query to that organization, JIT-provisioning the principal on
`GET /users/me`. Whatever organization is active in Clerk *is* the tenant.

Today `apps/web/src/routes/_authed.tsx` resolves a "pending" session (signed in,
no active org) by calling `setActive` on the **first** membership and never
revisits the choice. `apps/web/src/lib/auth.tsx` loads the principal once into a
context. There is no UI to change organizations, and no searchable select in the
library — `select.tsx` wraps Base UI's `Select`, which has no text filtering.

Constraints:

- The library's idiom is a thin, token-styled wrapper that re-exports Base UI
  compound parts (see `select.tsx`, `dropdown-menu.tsx`) — new primitives should
  follow it rather than invent a different shape.
- Base UI is on a release candidate; its combobox parts are present in the
  installed version (`@base-ui-components/react/combobox`) and no dependency is
  added.
- All cached web-API data is tenant-scoped, so switching organizations must not
  leave any of it on screen.

## Goals / Non-Goals

**Goals:**

- A generic `Combobox` primitive in the UI library that any future picker
  (vendors, companies, categories, accounts) can use unchanged.
- An organization switcher in the app shell that lists the user's memberships,
  filters by name, and activates the chosen one through Clerk.
- A single, reliable reset of tenant-scoped state when the active organization
  changes — regardless of what triggered the change.

**Non-Goals:**

- Creating organizations, inviting members, or any org-settings UI.
- Server-side org resolution or an API endpoint listing memberships — Clerk is
  the source of truth for membership.
- Remote/async search (fetch-as-you-type) inside the combobox; only a loading
  state for externally-loaded items is in scope.
- List virtualization and multi-select. Base UI supports both; wiring them is
  deferred until a screen needs them.
- Persisting the last-used organization beyond what Clerk's session already does.

## Decisions

### 1. Wrap Base UI's `Combobox` compound parts, mirroring `select.tsx`

`apps/web/src/components/ui/combobox.tsx` re-exports styled parts:
`Combobox` (Root), `ComboboxInput`, `ComboboxTrigger`, `ComboboxValue`,
`ComboboxContent` (Portal + Positioner + Popup, as `SelectContent` does),
`ComboboxList`, `ComboboxItem`, `ComboboxEmpty`, `ComboboxStatus`,
`ComboboxGroup`, `ComboboxGroupLabel`, `ComboboxClear`. The list is a separate
part rather than folded into `ComboboxContent`, because Base UI requires
`Empty` (and a search input, for popup-anchored triggers) to sit beside the list
inside the popup, not within it. Styling reuses the existing token classes
(`inputClassName`, `shadow-popover`, `data-[highlighted]:bg-muted`) so it is
visually identical to `Select`.

*Why*: Base UI's Root already provides the generic behaviour we would otherwise
hand-roll — `items` (flat or grouped), a default `filter`, `filteredItems` for
caller-owned filtering, `itemToStringLabel`, `isItemEqualToValue`, controlled and
uncontrolled `value`, and `autoHighlight`. Generic over `Value`, so items can be
strings or objects.

*Alternative considered*: a single closed component
(`<Combobox items getLabel value onValueChange />`). Rejected — it cannot express
the two shapes we already need (a workspace switcher whose trigger is a branded
button, and a plain form field), and the library has no other closed component.
Callers who want the simple case get it in ~10 lines with the parts. Each part
still accepts Base UI's `render` prop, so the trigger can be swapped wholesale
without forking.

*Filtering*: default to Base UI's built-in contains matching on the item label,
overridable per call via `filter` (or `filteredItems` for caller-owned filtering).
No custom filter code in the library.

### 2. `OrgSwitcher` lives in `apps/web/src/components/org-switcher.tsx`

App-specific, not part of the design system (which stays domain-free, like
`components/dashboard/`). It reads memberships from
`useOrganizationList({ userMemberships: { pageSize: 50 } })`, renders the active
organization's name, and on selection calls
`setActive({ organization: <id> })`.

- **0–1 memberships** → static label, no popup (spec: "Single membership is not a
  picker").
- **Memberships still loading** → skeleton/loading label.
- **`setActive` rejects** → the previous org stays active and a toast reports the
  failure (`useToast` already exists).

*Placement*: the sidebar header, beside the product mark — it is workspace-level
context that belongs next to navigation, and the topbar right side is already the
user menu plus theme toggle. `_authed/index.tsx` composes the shell today; the
switcher is added there.

### 3. Reset on `orgId` change, not in the click handler

The reset lives in `AuthProvider` (`lib/auth.tsx`) as an effect keyed on
`useAuth().orgId`: when it changes from a previously seen value, call
`queryClient.clear()`, and the authenticated subtree is remounted by keying it on
`orgId`.

*Why not do it inside the switcher's `onValueChange`*: the active org can also
change from Clerk's own flows, another browser tab, or the pending-org activation
in `_authed.tsx`. Keying the reset to the observed `orgId` covers every path with
one code path.

*Why `clear()` over threading `orgId` into every query key*: one line in one place
versus editing every `queryOptions` factory (`lib/reports.ts`, `lib/users.ts`, and
everything added later) and trusting future code to remember. All cached data is
tenant-scoped, so there is nothing worth keeping across a switch.

*Why also remount*: a request issued with the old token can resolve after the
clear and repopulate a mounted observer with previous-tenant data. Remounting the
subtree on `orgId` unmounts those observers, so late responses land nowhere. The
codebase already uses this idiom (`<UserMenu key={principal.id} />`).

*Navigation*: after a successful switch the app navigates to the dashboard root.
A deep link (e.g. an invoice id) is meaningless in another tenant and would
produce a 404/403 immediately after switching.

### 4. One source of memberships

`_authed.tsx` already calls `useOrganizationList` for pending-org activation. The
switcher uses the same hook with the same options so Clerk dedupes the request;
the activation effect keeps its existing "activate first membership once"
behaviour and gains nothing from the switcher.

### 5. Testing

- Combobox: extend `apps/web/src/components/ui/ui.test.tsx` (vitest + RTL,
  jsdom) — filtering narrows options, selection reports the value and closes,
  keyboard select/Escape, empty state, label association.
- OrgSwitcher: a component test mocking `useOrganizationList`/`useAuth` covering
  multi-membership switch (asserts `setActive` called with the chosen id), the
  single-membership static label, filtering, and the failure path.
- Cache reset: assert that an `orgId` change clears the query client and the
  principal is refetched.
- `/ui` kitchen-sink route gains a Combobox section (spec requirement).

## Risks / Trade-offs

- **Clerk paginates memberships** (default page size 10) → request `pageSize: 50`;
  users past that are vanishingly rare in this product, and infinite loading can
  be added behind the same component later without changing its API.
- **`queryClient.clear()` is a blunt reset** — every visible query refetches, so a
  switch costs a full reload of the page's data. Accepted: switching tenants is
  rare and correctness beats a warm cache.
- **Late responses from the old token** → mitigated by remounting the authed
  subtree on `orgId` (decision 3); without the remount, `clear()` alone is not
  sufficient.
- **Base UI is at `1.0.0-rc.0`** — combobox part names or props may shift before
  1.0 → the wrapper is the single place to absorb that, exactly as `select.tsx`
  does today.
- **Switching into a suspended organization** returns 403 from the web API → the
  existing error state renders; a dedicated "organization suspended" screen is out
  of scope here.
- **Combobox scope creep** — grouping, clear button, and status are exported but
  unused by the switcher. Kept because they are free (Base UI parts) and are what
  makes the primitive reusable; each is exercised on `/ui`.

## Migration Plan

Purely additive frontend change: no schema, API, or configuration changes, and
nothing to migrate. `pnpm build` + `pnpm test` in `apps/web/` gate it; rollback is
reverting the commit. The switcher degrades to today's behaviour (a static
organization label) for single-membership users, which is every user until
multi-org accounts exist.

## Open Questions

- Should the switcher show the Clerk organization logo/avatar next to the name?
  Deferred — trivial to add once brand assets exist for orgs.
- Should a user's role in each organization be shown in the list rows? Clerk
  membership carries it; omitted for now to keep the row a single line.
