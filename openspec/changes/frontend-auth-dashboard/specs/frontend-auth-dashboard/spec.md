## ADDED Requirements

### Requirement: Clerk authentication in the frontend

The frontend SHALL integrate Clerk via `@clerk/tanstack-react-start`, wrapping
the app in a `ClerkProvider` so a session exists and the app can obtain the
Clerk session JWT that the web API verifies. Configuration SHALL come from
`VITE_CLERK_PUBLISHABLE_KEY`.

#### Scenario: Provider initializes the session

- **WHEN** the app loads with a valid publishable key
- **THEN** Clerk initializes and the current session state (signed in or out) is
  available to the app

#### Scenario: Missing configuration is surfaced

- **WHEN** the publishable key is absent
- **THEN** the app fails with a clear, readable configuration error rather than a
  blank screen

### Requirement: Custom sign-in screen

The frontend SHALL provide a `/sign-in` page built from the in-house UI library
(Form, Input, Button) that authenticates through Clerk's `useSignIn`, supporting
email + password and, when enabled on the instance, a Google OAuth option. It
SHALL NOT use Clerk's prebuilt sign-in widget.

#### Scenario: Successful password sign-in

- **WHEN** a user submits valid email and password
- **THEN** the Clerk session becomes active and the user is redirected to the
  dashboard

#### Scenario: Invalid credentials

- **WHEN** a user submits credentials Clerk rejects
- **THEN** an error message is shown on the form and the user remains on
  `/sign-in`

#### Scenario: OAuth sign-in

- **WHEN** Google OAuth is enabled and the user chooses it
- **THEN** the user is taken through Clerk's OAuth redirect and, on return with a
  completed session, lands on the dashboard

### Requirement: Protected routes redirect unauthenticated users

Authenticated application routes SHALL be nested under a guarded layout whose
`beforeLoad` verifies the Clerk session server-side; unauthenticated requests
SHALL be redirected to `/sign-in`. A sign-out action SHALL clear the session and
return the user to `/sign-in`.

#### Scenario: Unauthenticated access is redirected

- **WHEN** a signed-out user navigates to a protected route (e.g. the dashboard)
- **THEN** they are redirected to `/sign-in` before the protected content renders

#### Scenario: Authenticated access is allowed

- **WHEN** a signed-in user navigates to a protected route
- **THEN** the route renders

#### Scenario: Sign out

- **WHEN** a signed-in user activates sign-out
- **THEN** the Clerk session is cleared and they are returned to `/sign-in`

### Requirement: Authenticated API access to the web API

The frontend SHALL call the web API through a typed client that attaches the
Clerk session token as a Bearer credential and targets `VITE_API_BASE_URL`,
using TanStack Query for caching and request state. Non-2xx responses SHALL raise
a typed error the UI can render.

#### Scenario: Requests carry the session token

- **WHEN** the client issues a request to the web API while signed in
- **THEN** the request includes `Authorization: Bearer <clerk session token>`

#### Scenario: API error is surfaced

- **WHEN** the web API returns a non-2xx response
- **THEN** the client raises a typed error and the calling UI shows an error
  state rather than crashing

### Requirement: Current principal available to the app

The guarded layout SHALL load the current principal from `GET /users/me` and make
it available to descendants, exposing at least `email`, `name`, `role`,
`isSystemAdmin`, and `organizationId`.

#### Scenario: Principal is loaded and displayed

- **WHEN** the dashboard renders for a signed-in user
- **THEN** the topbar shows the user's identity sourced from `/users/me`

#### Scenario: Role foundation for admin routes

- **WHEN** the principal is available
- **THEN** an `isSystemAdmin` flag and a reusable system-admin guard are exposed
  for future `/admin/*` routes, without any `/admin/*` page existing yet

### Requirement: Dashboard renders live reporting data

The dashboard SHALL render inside the themed AppShell and display live figures
from `GET /reports/*` (org-wide, no company filter) — stat cards plus one
breakdown table — with loading, empty, and error states. Monetary figures SHALL
be presented grouped by currency and never summed across currencies.

#### Scenario: Data is shown

- **WHEN** the org has reportable data and the dashboard loads
- **THEN** stat cards and a breakdown table display values from the reporting
  endpoints, with amounts grouped by currency

#### Scenario: Loading state

- **WHEN** the reporting queries are in flight
- **THEN** the dashboard shows loading placeholders (skeletons) rather than empty
  or broken content

#### Scenario: Empty state

- **WHEN** the org has no reportable data yet
- **THEN** the dashboard shows an explicit empty state instead of zeros that look
  like an error

#### Scenario: Currency separation

- **WHEN** entries or spend span multiple currencies
- **THEN** totals are shown per currency and are not combined into a single sum
