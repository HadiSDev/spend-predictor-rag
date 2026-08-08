## Context

The frontend today is read-only. `_authed/index.tsx` is the single authenticated
page: it *defines* the app shell inline, loads two report queries, and renders
them. `lib/api-client.ts` exposes one method — `get` — and `ApiError` carries only
a status and a synthetic `Request to <path> failed with <status>` message. There
is no mutation anywhere in the codebase, no form submitted to the web API, and no
role-gated control.

Two systems own the data this page administers:

| Data | Owner | Access |
| --- | --- | --- |
| User identity (name, avatar, emails, password, sessions, OAuth) | **Clerk** | Clerk client SDK |
| Organization membership, roles, invitations | **Clerk** | Clerk client SDK (`useOrganization`) |
| Organization profile (name, slug, status) | **web_api** | `GET`/`PATCH`/`DELETE /api/v1/organization` |
| Companies | **web_api** | `GET`/`POST /api/v1/companies`, `PATCH`/`activate`/`deactivate` |
| Local `User` / `Organization` rows | **web_api**, *derived* | written only by the Clerk webhook + JIT provisioning |

That last row is the constraint that shapes most of this design: the local `User`
table is a projection, not a source. A person invited today has no local row until
they first sign in, and a role changed in Clerk lands locally only when the
webhook is processed. `GET /api/v1/users` therefore cannot back a member
directory that shows pending members or reflects a role change immediately.

Constraints inherited from the codebase: Base UI + Tailwind v4 house components,
`react-hook-form` for forms (**no** `zod` and no resolver package installed),
TanStack Router file-based routing with a generated `routeTree.gen.ts`, TanStack
Query for server state, and Vitest tests that render components with props rather
than standing up a router or a network mock.

## Goals / Non-Goals

**Goals**

- One settings area covering personal, organization, and company administration,
  reachable from the sidebar and linkable per section.
- Establish the app's write conventions once: a mutating API client, a
  query/mutation module per resource, form + error + toast handling, and
  role-gated controls — so the invoice and ERP pages that follow copy rather than
  invent.
- Keep the two sources of truth explicit and never write to the derived local
  tables from the UI.
- Match the API's authorization rules in the UI without pretending client gating
  is enforcement.

**Non-Goals**

- ERP integration management (connect / disconnect / account sync toggles). The
  endpoints exist; the surface is large enough to deserve its own change.
- Any new `web_api` endpoint, schema, or migration.
- An organization *switcher* — that is `frontend-org-switcher`'s job, and this
  change must not introduce a competing one.
- Organization creation, and cross-tenant system-admin administration (a system
  admin still administers the org their token is scoped to).
- Notification preferences, API keys, billing.

## Decisions

### Route shape: a layout route with child routes, not local tab state

`_authed/settings.tsx` is a layout route rendering the tab bar plus `<Outlet />`;
`_authed/settings/profile.tsx`, `organization.tsx`, and `companies.tsx` are the
sections; `_authed/settings/index.tsx` redirects to `profile`.

Alternative considered: a single `settings.tsx` with `Tabs` holding local state.
Rejected — the spec requires a linkable, reload-surviving section, and local state
gives neither. Child routes also let each section own its own data loading, so
opening Profile never fetches companies.

The tab bar keeps the existing `Tabs`/`TabsList`/`TabsTab` visuals (including the
sliding indicator) but each `TabsTab` renders a router `<Link>` through Base UI's
`render` prop, and `Tabs` `value` is derived from the matched route rather than
held in state. This keeps navigation real (middle-click, back button) while
preserving the component library's look.

### The shell moves to `_authed.tsx`

The sidebar/topbar currently live in `DashboardShell` inside the dashboard route.
Extract to `#/components/app-shell.tsx` and render it in `_authed.tsx` wrapping
`<Outlet />`, so it mounts once and survives navigation. Sidebar items become
`<Link>`s using the existing `sidebarNavItemClass(active)` helper with `active`
driven by `useMatchRoute` / `Link`'s `activeProps`; Invoices and Vendors stay
disabled as non-links.

Alternative considered: each page renders its own shell. Rejected — it remounts
the sidebar (losing scroll and any future state) on every navigation and
duplicates the topbar in every future page.

This collides with `frontend-org-switcher`, which also edits `_authed.tsx` and the
sidebar header. Whichever lands second rebases; the merge surface is one file and
the switcher's insertion point (`SidebarHeader`) is untouched by this change.

### API client: one internal `request`, four verbs, richer errors

```ts
interface ApiClient {
  get<T>(path, params?): Promise<T>
  post<T>(path, body?, params?): Promise<T>
  patch<T>(path, body?, params?): Promise<T>
  del<T>(path, params?): Promise<T>
}
```

All four funnel through the existing private `request`, extended with `method`
and `body`; `Content-Type: application/json` is set only when a body is present,
and `204` resolves to `undefined` without parsing. `ApiError` gains a `detail`
getter that pulls FastAPI's `{"detail": "..."}` out of the already-parsed error
body (and handles the `detail: [{msg, loc}]` array shape 422 uses), falling back
to the current generic message. `detail` — not `message` — is what UI code shows.

`del` rather than `delete` because `delete` is a reserved word and reads badly as
a method name in TS object literals.

### One module per resource, exporting query options *and* mutation options

`lib/organization.ts` and `lib/companies.ts` follow `lib/reports.ts`'s existing
`queryOptions` factory shape and add mutation factories that take the
`ApiClient` and the `QueryClient`:

```ts
organizationQueryOptions(api)                 // ['organization']
updateOrganizationMutation(api, qc)           // invalidates ['organization'] + ['users','me']
companiesQueryOptions(api, { includeInactive })// ['companies', { includeInactive }]
createCompanyMutation(api, qc)                // invalidates ['companies']
```

Invalidate-and-refetch, not optimistic updates. Rationale: these are low-frequency
administrative writes where correctness beats perceived latency, and the server
normalizes values (slug, trimmed names, `deactivated_at`) that an optimistic patch
would guess wrong. `['companies']` is invalidated as a prefix so both the active
and include-inactive caches refresh.

Any mutation that can change the caller's own role or organization also
invalidates `['users','me']`, so `usePrincipal()` and every gate derived from it
re-derive.

### Membership comes from Clerk, org profile from the web API

The Members panel uses `useOrganization({ memberships: true, invitations: true })`
and Clerk's `organization.inviteMember` / `updateMember` / `removeMember` /
`invitation.revoke`. `GET /api/v1/users` is deliberately **not** used.

Alternative considered: read the directory from `GET /api/v1/users` and write
through Clerk. Rejected — a member invited but never signed in has no local row,
and a role change would appear to fail until the webhook lands, producing a UI
that contradicts itself. Reading and writing the same source keeps the panel
internally consistent; the webhook still reconciles the local projection for the
API's own authorization.

Consequence: member counts in this panel may briefly differ from anything else
built on the local `User` table. That is correct — Clerk is ahead, the projection
catches up.

### Role gating derives from the principal, in one place

`lib/auth.tsx` gains pure helpers beside `usePrincipal`:

```ts
canManageOrganization(p)  // p.isSystemAdmin || p.role === 'admin'
canManageCompanies(p)     // p.isSystemAdmin || p.role === 'admin' || p.role === 'moderator'
```

mirroring `require_org_admin` and `require_management` in `web_api/deps.py`. Panels
read them and render read-only variants — not hidden panels — except the danger
zone, which is hidden outright because an unauthorized user has nothing to read
there. A comment in both files points at the other, since the two rule sets must
stay in step; divergence degrades to a 403 the UI already handles, never to a
privilege escalation.

### Forms: react-hook-form with built-in rules, no new validation dependency

Fields use the existing `Form`/`FormField`/`FormMessage` components with RHF's
native `rules` (`required`, `maxLength`, `pattern`, `validate`). Adding `zod` +
`@hookform/resolvers` for four short forms is not worth the dependency; if a
later change needs shared schemas, that is the moment to introduce it.

Server errors map onto fields through `setError`: an `ApiError` with 409 on the
org form targets `slug`; a Clerk `ClerkAPIError` carries `meta.paramName`, which
maps to the field of the same name. Anything unmapped becomes a form-level error
plus a toast. Submit is `disabled={!formState.isDirty || formState.isSubmitting}`,
matching the spec's interaction contract.

### Suspension: detect the suspended state rather than special-case the success path

`DELETE /api/v1/organization` makes every subsequent API call return
403 `"Organization is suspended"` (`web_api/deps.py:current_user`). Rather than
scripting a bespoke post-suspend flow, `AuthProvider` learns to recognize that
error from `GET /users/me` and render an explicit "Organization suspended" screen
with a sign-out action. The danger-zone action then just calls the endpoint and
clears the query cache; the app converges on the suspended screen on its own.

This also fixes an existing hole: a user whose org was suspended elsewhere
currently sees the generic "Couldn't load your account" screen.

### Presentational panels, thin route containers

Each section splits into a container (route component: queries, mutations,
gating) and a presentational panel taking data plus callbacks as props. This is
what makes the existing test style work — `dashboard.test.tsx` renders
`DashboardBody` with plain arrays and asserts DOM, with no network or router. New
tests follow it: panels tested with props and `vi.fn()` handlers; only the small
Clerk-facing pieces need the `vi.mock('@clerk/tanstack-react-start', …)` pattern
already established in `sign-in.test.tsx`.

## Risks / Trade-offs

- **Two sources of truth drift** (a role changed in Clerk, webhook delayed) →
  membership is read and written in Clerk only, so the panel is self-consistent;
  `['users','me']` is invalidated after self-affecting changes so the API-side
  role the app gates on is refreshed too.
- **Client gating diverges from server rules** (`deps.py` changes, helpers don't)
  → helpers live in one file with a cross-reference comment, and every mutation
  path still renders a 403 as an error, so divergence is a cosmetic bug, never an
  authorization bypass.
- **Merge conflict with `frontend-org-switcher`** over `_authed.tsx` and the
  sidebar → both touch a small, well-known region; the second to land rebases,
  and this change adds no org-selection UI of its own.
- **Suspension is easy to reach and reversible only outside the app** (there is no
  restore endpoint) → admin-only, in a distinct danger zone, behind typed-name
  confirmation, with copy stating plainly that data is retained and access is
  blocked until restored.
- **Clerk SDK surface for invitations/roles varies by instance configuration**
  (allowed roles are an org setting) → role options are read from Clerk rather
  than hard-coded to the four known roles, so the UI cannot offer a role the
  instance rejects.
- **Avatar/image upload adds a file input and its failure modes** → size and type
  are validated client-side before upload and Clerk's error is surfaced verbatim;
  no cropping UI, which keeps the scope honest.
- **The settings area is the first write surface, so it carries the cost of the
  conventions** → accepted deliberately; the alternative is inventing them under
  time pressure in the invoice-verification page.

## Migration Plan

Purely additive on the frontend; no backend, schema, or data migration. The one
behavioural change to existing code is the shell extraction, which moves markup
without changing what it renders. `routeTree.gen.ts` is regenerated
(`pnpm generate-routes`). Rollback is reverting the branch — no state is written
that a rollback would strand, and the only externally visible side effects
(org rename, invitations, company records) are ordinary API/Clerk operations that
predate this change.

## Open Questions

- Should a `member`/`viewer` see the Members panel at all, or only admins? The
  spec currently shows it read-only to everyone in the org, which matches how the
  API treats `GET /users`. Worth a look during implementation review.
- Clerk's allowed org roles are instance-configured; if the instance exposes roles
  beyond the four the API knows (`admin`, `moderator`, `member`, `viewer`), the UI
  will offer them and the webhook will store an unfamiliar value. Confirm the
  Clerk instance's role list matches before enabling role editing.
