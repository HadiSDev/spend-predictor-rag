## Why

The `frontend/` app has a themed component library but no application yet — no
way to authenticate or see any data. To make the admin panel usable we need the
**base**: sign in against the existing Clerk-backed web API, then land on a
dashboard that renders the org's real spend figures in the ERPSAA look. This is
the foundation every later screen (invoices, vendors, `/admin/*`) builds on.

## What Changes

- **Clerk auth in the frontend** — add `@clerk/tanstack-react-start` and a
  `ClerkProvider`, so the app has a session and can mint the session JWT the web
  API already verifies. Requires `VITE_CLERK_PUBLISHABLE_KEY`.
- **Custom login screen** — a `/sign-in` page built from our own UI library
  (Form + Input + Button), driving Clerk's `useSignIn` (email + password, and a
  Google OAuth button). No prebuilt Clerk widget; the page matches the theme.
- **Authenticated route protection** — an `_authed` layout route whose
  `beforeLoad` redirects unauthenticated users to `/sign-in` and loads the
  current principal (`GET /users/me`) into router context. A sign-out action
  clears the Clerk session.
- **Typed, authenticated API client** — a small fetch wrapper that attaches the
  Clerk token and a `baseURL` (`VITE_API_BASE_URL`), plus TanStack Query wired
  through the existing SSR-query integration for caching/loading/error states.
- **Dashboard** (`/` inside `_authed`) — the themed AppShell (sidebar + topbar
  with the signed-in user + theme toggle) rendering **live** figures: stat cards
  and a breakdown table sourced from `GET /reports/*` and `GET /users/me`, with
  proper loading skeletons and empty states. Money stays grouped by currency
  (never summed across), matching the reporting API.
- **Role-aware foundation (no admin pages yet)** — the principal in context
  exposes `isSystemAdmin`; a reusable guard is provided so `/admin/*` can be
  added later. Building `/admin/*` screens is **out of scope** for this change.

## Capabilities

### New Capabilities
- `frontend-auth-dashboard`: authenticated frontend base — Clerk sign-in, a
  protected route shell that loads the current principal, an authenticated API
  client, and a dashboard rendering live reporting data in the ERPSAA theme,
  with a role-aware foundation for future `/admin/*` routes.

### Modified Capabilities

## Impact

- `frontend/` only. New deps: `@clerk/tanstack-react-start`, `@tanstack/react-query`
  (+ the already-present `@tanstack/react-router-ssr-query`). New env:
  `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_API_BASE_URL` (documented in
  `frontend/.env.example`).
- New files under `frontend/src/`: `routes/sign-in.tsx`, `routes/_authed.tsx`
  (guard), `routes/_authed/index.tsx` (dashboard), `lib/api-client.ts`,
  `lib/auth.ts` (principal loader + `useAuth`/role helpers), `lib/reports.ts`
  (query options), and `ClerkProvider`/`QueryClientProvider` wiring in
  `router.tsx` + `routes/__root.tsx`.
- **Backend**: no code change. Relies on the existing `GET /users/me` and
  `GET /reports/*` endpoints and the already-added CORS support
  (`WEB_API_CORS_ORIGINS` must include the frontend origin in dev).
- **Non-goals:** `/admin/*` pages, invoices/vendors/companies screens, sign-up /
  org-provisioning flows, and write actions — later changes.
