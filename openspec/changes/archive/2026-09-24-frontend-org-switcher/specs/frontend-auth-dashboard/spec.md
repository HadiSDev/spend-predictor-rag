## ADDED Requirements

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
