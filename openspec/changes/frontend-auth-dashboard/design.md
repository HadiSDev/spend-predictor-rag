## Context

The web API (`web_api/`) is a Clerk **resource server**: it verifies Clerk
session JWTs against Clerk's JWKS and derives the principal (role +
`is_system_admin` + `organization_id`) from the token and DB. It already exposes
`GET /users/me` and `GET /reports/*` (org-scoped aggregates; `company_id`
optional → org-wide), and opt-in CORS via `WEB_API_CORS_ORIGINS`.

The `frontend/` app is TanStack Start (SSR) + TanStack Router (file-based) with a
themed Base-UI component library and an `AppShell`. It currently has no auth, no
API client, and no real pages — only `/` and `/ui`. This change adds the base:
authenticate with Clerk, protect routes, and render a live dashboard.

Decisions were pre-agreed with the user: **custom login form** (our components +
Clerk hooks, not the prebuilt widget) and **live reporting data** on the
dashboard.

## Goals / Non-Goals

**Goals:**
- Sign in / sign out against the existing Clerk instance; obtain the session JWT
  the web API already trusts.
- A custom, on-theme `/sign-in` page (email+password + Google OAuth).
- Protect authenticated routes; unauthenticated users are redirected to sign-in.
- An authenticated, typed API client + TanStack Query for data fetching.
- A dashboard rendering live `GET /reports/*` + `GET /users/me` figures in the
  ERPSAA theme, with loading/empty/error states, grouped by currency.
- A role-aware foundation (`isSystemAdmin` available to the app + a reusable
  guard) so `/admin/*` can be added later.

**Non-Goals:**
- Any `/admin/*` page or admin-only feature (only the guard foundation).
- Invoices/vendors/companies screens, write actions, filters/date-range UI.
- Sign-up, org creation/provisioning, invitations, profile editing.
- Charts/visualizations beyond stat cards + a breakdown table (kept minimal).

## Decisions

### 1. Clerk SDK: `@clerk/tanstack-react-start` (SSR-aware)
Use the official TanStack Start integration, not SPA-only `@clerk/clerk-react`.
It provides `ClerkProvider`, client hooks (`useSignIn`, `useAuth`, `useClerk`),
and a server entry (`@clerk/tanstack-react-start/server`'s `auth()`) that makes
`beforeLoad` redirects work during SSR without a client round-trip.
*Alternative:* `@clerk/clerk-react` — simpler but no server auth; a protected
route would flash before the client resolves the session. Rejected.

### 2. Custom sign-in via `useSignIn`
`/sign-in` is our own `Form`/`Input`/`Button` layout. **Implementation note:** the
installed `@clerk/tanstack-react-start` (1.4.x) exposes the newer *future/signal*
`useSignIn` — `{ signIn: SignInFutureResource, fetchStatus, errors }` — not the
classic `{ isLoaded, signIn, setActive }`. So the flow is: email+password via
`signIn.password({ identifier, password })`, then, when `signIn.status ===
'complete'`, `signIn.finalize()` to activate the session, then
`navigate({ to: '/' })`. Google uses `signIn.sso({ strategy: 'oauth_google',
redirectUrl, redirectCallbackUrl })` with an SSO-callback route. Errors come back
as `{ error }` results and render in an alert; `fetchStatus === 'fetching'` gates
submission. MFA / password-reset statuses are surfaced as "additional
verification required" and deferred (non-goal).
*Alternative:* Clerk `<SignIn/>` — faster but not our theme; user chose custom.

### 3. Route protection: pathless `_authed` layout + server `auth()`
A pathless `routes/_authed.tsx` layout route guards everything nested under it.
Its `beforeLoad` calls a `createServerFn` that runs `auth()`; if not
authenticated it `throw redirect({ to: '/sign-in' })`. The dashboard is
`routes/_authed/index.tsx`; future `/admin/*` nests as `routes/_authed/admin/*`.
*Alternative:* client-only `<SignedIn/>`/`<RedirectToSignIn/>` — simpler but
renders a protected shell first. Rejected for the guard; `<SignedIn/>` may still
be used for small conditional UI bits.

### 4. API auth: client bearer token + TanStack Query
A `lib/api-client.ts` wrapper reads `VITE_API_BASE_URL` and attaches
`Authorization: Bearer ${await getToken()}` (from `useAuth()`), parses JSON, and
throws a typed `ApiError` on non-2xx. Data is fetched with **TanStack Query**
(new dep) through the existing `@tanstack/react-router-ssr-query` integration, so
we get caching, `isLoading`/`isError`, and dedup. Query keys namespace by
endpoint + params.
*Alternative:* fetch everything server-side via `createServerFn` proxying with
`auth().getToken()`. More SSR-correct but heavier; deferred — client fetch is
fine for an authenticated admin panel and keeps this slice small.

### 5. Principal + roles: `/users/me` in context
The `_authed` layout fetches `GET /users/me` via Query and provides it through an
`AuthProvider` (`usePrincipal()` → `{ id, email, name, role, isSystemAdmin,
organizationId }`). The topbar shows the user; a `requireSystemAdmin` helper
(throws/redirects when `!isSystemAdmin`) is exported for future `/admin/*`
`beforeLoad`. No admin route is added now.
*Note:* server-side role gating for `/admin/*` will fetch the principal in the
guard's server fn later; for this slice role is a client-side concern only.

### 6. Dashboard content (live)
Inside the `AppShell`: a row of **StatCards** and a **DataTable** breakdown,
sourced org-wide (no `company_id`):
- Stat cards from `GET /reports/entries-summary` (ledger totals **per currency**)
  and counts derivable from the same payloads.
- Breakdown table from `GET /reports/spend-by-category` (top categories) — or
  `spend-by-vendor`; one table for the base.
Every money figure is rendered **grouped by currency** (the API never sums across
currencies). Loading → `Skeleton`s; empty (no data yet) → an empty state; error →
inline message. `NumberInput`/formatting utilities render amounts.

### 7. Config & env
New env in `frontend/.env.example`: `VITE_CLERK_PUBLISHABLE_KEY` (required) and
`VITE_API_BASE_URL` (e.g. `http://localhost:8000`). Dev requires the API's
`WEB_API_CORS_ORIGINS` to include the frontend origin (`http://localhost:3000`).

## Risks / Trade-offs

- **Clerk publishable key / instance not configured for the frontend** → app
  can't initialize. *Mitigation:* document the env clearly; `ClerkProvider`
  surfaces a readable error; the key is the same Clerk instance the API already
  targets.
- **CORS/token mismatch in dev** (wrong origin or audience) → 401s from the API.
  *Mitigation:* document `WEB_API_CORS_ORIGINS` + note that `CLERK_AUDIENCE`, if
  set on the API, must match the token; default dev uses no audience.
- **Custom sign-in misses Clerk flows** (MFA, verification, password reset) →
  users on those factors can't complete sign-in. *Mitigation:* handle the
  common `complete` + `needs_first_factor` paths and OAuth; explicitly defer
  MFA/reset to a later change (documented non-goal).
- **Client-side token fetch on every request** adds latency / relies on Clerk
  being loaded. *Mitigation:* `getToken()` is cached by Clerk; Query dedups;
  acceptable for an internal panel. Revisit with server fns if needed.
- **Empty database** makes the "live" dashboard look bare. *Mitigation:*
  first-class empty states so it reads as "no data yet", not broken.

## Migration Plan

Frontend-only, additive; no backend or DB change and no data migration. Rollout:
add deps → wire `ClerkProvider`/`QueryClientProvider` → add `/sign-in`, `_authed`
guard, dashboard → point env at the Clerk instance + API. Rollback: revert the
frontend change; the API is unaffected. Behind a dev origin until deployed.

## Open Questions

- Which single breakdown table ships first — **spend-by-category** (assumed) or
  spend-by-vendor? (Category chosen unless told otherwise.)
- Is a Google OAuth provider enabled on the Clerk instance? If not, the OAuth
  button is hidden and email+password is the only method for this slice.
