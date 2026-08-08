## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Persistent application shell across authenticated routes

The themed application shell — sidebar, navigation, topbar, theme toggle, and
user menu — SHALL be owned by the authenticated layout rather than by any single
page, so every authenticated route renders inside it and the shell is not
remounted when navigating between routes. Sidebar navigation entries SHALL be
router links that navigate on activation, and the entry matching the current
route SHALL be rendered as active. Entries for pages that do not exist yet SHALL
remain visibly disabled.

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
