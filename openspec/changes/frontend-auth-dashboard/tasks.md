## 1. Deps, config & providers

- [x] 1.1 Add deps (Bun): `@clerk/tanstack-react-start`, `@tanstack/react-query`
- [x] 1.2 Add `frontend/.env.example` with `VITE_CLERK_PUBLISHABLE_KEY` and
  `VITE_API_BASE_URL`; read them via a typed `src/lib/env.ts`
- [x] 1.3 Wrap the app in `ClerkProvider` (root) and a `QueryClientProvider`
  (via `@tanstack/react-router-ssr-query`); keep existing Theme/Tooltip/Toast
  providers. Update `src/router.tsx` + `src/routes/__root.tsx`

## 2. Authenticated API client & data layer

- [x] 2.1 `src/lib/api-client.ts` — fetch wrapper: `VITE_API_BASE_URL`, attaches
  `Authorization: Bearer <getToken()>`, JSON parse, typed `ApiError` on non-2xx
- [x] 2.2 `src/lib/reports.ts` + `src/lib/users.ts` — TanStack Query options for
  `GET /users/me` and the `GET /reports/*` endpoints used by the dashboard
- [x] 2.3 Type the API responses (UserRead, Report rows) in `src/lib/types.ts`

## 3. Sign-in

- [x] 3.1 `src/routes/sign-in.tsx` — custom form (Form/Input/Button) via the
  Clerk future `useSignIn` API: `signIn.password()` → `signIn.finalize()` →
  navigate to `/`; Clerk `{ error }` rendered in an alert; `fetchStatus` gates
  submit. (Installed `@clerk/tanstack-react-start` exposes the future/signal
  hook, not the classic `create`/`setActive`.)
- [x] 3.2 Google OAuth button (`signIn.sso({ strategy: 'oauth_google' })`) + SSO
  callback route, shown only when `VITE_CLERK_GOOGLE_OAUTH` is enabled
- [x] 3.3 On-theme two-column / centered auth layout matching the ERPSAA look

## 4. Route protection & principal

- [x] 4.1 `src/routes/_authed.tsx` — pathless guarded layout: `beforeLoad`
  server fn runs Clerk `auth()`, `redirect({ to: '/sign-in' })` when signed out
- [x] 4.2 `src/lib/auth.tsx` — `AuthProvider` fetching `/users/me` (Query) +
  `usePrincipal()`; `isSystemAdmin`; `requireSystemAdmin` guard helper for
  future `/admin/*` (no admin page added)
- [x] 4.3 Sign-out action (`useClerk().signOut`) wired into the topbar user menu

## 5. Dashboard

- [x] 5.1 `src/routes/_authed/index.tsx` — dashboard inside `AppShell`; topbar
  shows the principal + theme toggle; sidebar nav (Dashboard active)
- [x] 5.2 Stat cards from `GET /reports/entries-summary` (org-wide), rendered
  **per currency**; amounts formatted with the number utilities
- [x] 5.3 Breakdown `DataTable` from `GET /reports/spend-by-category`
- [x] 5.4 Loading skeletons, empty state, and inline error state for each query

## 6. Verification

- [x] 6.1 `bunx tsc --noEmit` clean; `bun run build` succeeds
- [x] 6.2 Tests (Vitest + Testing Library): sign-in renders + shows an error on
  rejected credentials (Clerk mocked); dashboard renders stat cards from mocked
  report data and shows the empty state when reports are empty
- [ ] 6.3 Manual smoke (requires a configured Clerk instance + running web API +
  data): signed-out `/` → redirect to `/sign-in`; sign in → dashboard with live
  data; sign out → back to `/sign-in`. Steps documented in `frontend/README.md`;
  not yet run here (no live Clerk/API credentials in this environment).
- [x] 6.4 Update `frontend/README.md`: auth flow, env vars, API client, the
  `_authed` guard + role foundation
