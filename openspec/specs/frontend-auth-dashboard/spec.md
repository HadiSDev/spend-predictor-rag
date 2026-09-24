# frontend-auth-dashboard Specification

## Purpose
TBD - created by syncing change frontend-auth-dashboard. Update Purpose after archive.
## Requirements
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
using TanStack Query for caching and request state. The client SHALL support
reads (`GET`) and authenticated writes (`POST`, `PATCH`, `DELETE`) with JSON
request bodies, sending `Content-Type: application/json` when a body is present.
Non-2xx responses SHALL raise a typed error the UI can render, carrying the HTTP
status and, when the response body contains FastAPI's `detail`, that message —
so a caller can show the API's own explanation rather than a generic failure
string. A `204 No Content` response SHALL resolve without attempting to parse a
body.

#### Scenario: Requests carry the session token

- **WHEN** the client issues a request to the web API while signed in
- **THEN** the request includes `Authorization: Bearer <clerk session token>`

#### Scenario: API error is surfaced

- **WHEN** the web API returns a non-2xx response
- **THEN** the client raises a typed error and the calling UI shows an error
  state rather than crashing

#### Scenario: A write is performed

- **WHEN** the UI submits a create or update through the client
- **THEN** the request uses the corresponding method with a JSON body and the
  session token, and the parsed response is returned to the caller

#### Scenario: Error detail is preserved

- **WHEN** the web API rejects a write with a status and a `detail` message (for
  example 403 for an insufficient role or 409 for a duplicate slug)
- **THEN** the typed error exposes both the status and that message, and the UI
  can present the message to the user

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

### Requirement: Persistent application shell across authenticated routes

The themed application shell SHALL be owned by the authenticated layout rather
than by any single page — sidebar, navigation, topbar, theme toggle, and user
menu — so every authenticated route renders inside it and the shell is not
remounted when navigating between routes. Sidebar navigation entries SHALL be
router links that navigate on activation, and the entry matching the current
route SHALL be rendered as active. Entries for pages that do not exist yet SHALL
remain visibly disabled.

The navigation SHALL offer an **Entries** entry linking to the `/entries` route.
It replaces the previous disabled **Invoices** placeholder: entries are what the
ERP sync actually produces, and one spend event is several entries, so the entry
is the unit the navigation leads with. No Invoices entry SHALL be shown until an
invoice review page exists.

#### Scenario: Shell is shared by every authenticated page

- **WHEN** a signed-in user navigates from the dashboard to another
  authenticated route
- **THEN** the same shell persists, with the page content swapping inside it

#### Scenario: Active route is highlighted

- **WHEN** an authenticated route is open
- **THEN** the sidebar entry corresponding to it is marked active and the others
  are not

#### Scenario: Navigation happens through the router

- **WHEN** the user activates an enabled sidebar entry
- **THEN** the router navigates to that route and the URL updates, without a full
  page load

#### Scenario: Entries is a working navigation entry

- **WHEN** a signed-in user activates the Entries entry
- **THEN** the router navigates to `/entries`, the entry is marked active, and no
  disabled Invoices entry is present

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

### Requirement: Organization switcher in the app shell

Every authenticated page SHALL display the active organization in the app shell
and, when the signed-in user belongs to more than one organization, SHALL let the
user switch to another of their memberships from there. The list SHALL contain
exactly the user's own Clerk organization memberships, presented in a searchable
combobox from the UI library so long membership lists stay usable.

The switch SHALL be performed through Clerk's active-organization API so the
session token carries the new `orgId` claim, which is what scopes every
subsequent web-API request.

#### Scenario: User with multiple memberships switches organization

- **WHEN** a user who belongs to more than one organization picks a different
  organization from the switcher
- **THEN** that organization becomes the active one for the session and the app
  shell shows it as active

#### Scenario: Single membership is not a picker

- **WHEN** the signed-in user belongs to exactly one organization
- **THEN** the shell displays that organization's name as a static label with no
  interactive picker

#### Scenario: Memberships are filtered by typing

- **WHEN** the user opens the switcher and types part of an organization's name
- **THEN** only memberships matching that text are listed

#### Scenario: Memberships are still loading

- **WHEN** the switcher renders before the membership list has resolved
- **THEN** it shows a loading placeholder instead of an empty or misleading list

### Requirement: Switching organization re-scopes the session data

Switching the active organization SHALL leave no data from the previous
organization visible. On a successful switch the app SHALL discard cached
tenant-scoped query data and reload the current principal from `GET /users/me`,
so the displayed role, organization id, and all figures belong to the newly
active organization.

#### Scenario: Cached tenant data is discarded

- **WHEN** the active organization changes
- **THEN** cached web-API query results from the previous organization are removed
  and the visible data is refetched for the new organization

#### Scenario: Principal reflects the new organization

- **WHEN** the active organization changes
- **THEN** `GET /users/me` is reloaded and the principal's `organizationId` and
  `role` are those of the newly active organization

#### Scenario: Failed switch keeps the current organization

- **WHEN** activating the chosen organization fails
- **THEN** the previously active organization remains active, an error is
  surfaced to the user, and cached data is not discarded

