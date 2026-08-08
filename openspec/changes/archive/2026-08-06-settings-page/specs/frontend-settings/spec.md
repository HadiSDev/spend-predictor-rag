## ADDED Requirements

### Requirement: Settings area with linkable tabs

The frontend SHALL provide a settings area at `/settings` inside the
authenticated layout, presenting three sections — **Profile**, **Organization**,
and **Companies** — as tabs. The active section SHALL be encoded in the URL
(`/settings/profile`, `/settings/organization`, `/settings/companies`) so it is
linkable, shareable, and preserved across reload and browser navigation.
`/settings` SHALL resolve to the Profile section. The settings area SHALL render
inside the shared application shell, and the sidebar's Settings item SHALL be
enabled and marked active while any settings route is open.

#### Scenario: Opening settings

- **WHEN** a signed-in user activates Settings in the sidebar
- **THEN** the app navigates to the settings area, the Profile section renders,
  and the Settings nav item is highlighted as active

#### Scenario: Section is reflected in the URL

- **WHEN** the user selects the Organization tab
- **THEN** the URL becomes `/settings/organization` and a reload or a back
  navigation returns to that same section

#### Scenario: Deep link to a section

- **WHEN** the user loads `/settings/companies` directly
- **THEN** the Companies section renders with its tab selected, without first
  flashing another section

### Requirement: Personal profile editing

The Profile section SHALL let the signed-in user edit their own identity through
Clerk's client SDK using the in-house UI library — it SHALL NOT embed Clerk's
prebuilt `<UserProfile />` widget. It SHALL support editing first and last name
and uploading or removing the profile image. On success the change SHALL be
reflected immediately in the topbar user menu without a page reload.

#### Scenario: Name is updated

- **WHEN** the user changes their name and saves
- **THEN** the update is written to Clerk, a success confirmation is shown, and
  the topbar shows the new name

#### Scenario: Avatar is uploaded

- **WHEN** the user selects an image file for their avatar
- **THEN** the image is uploaded to Clerk and the new avatar appears in the form
  and the topbar

#### Scenario: Update is rejected

- **WHEN** Clerk rejects the update (for example an invalid image or a
  server error)
- **THEN** the form shows the returned error message and the previous values
  remain

### Requirement: Email address management

The Profile section SHALL let the user list their email addresses with their
verified and primary status, add a new address, confirm it with the
verification code Clerk emails, promote a verified address to primary, and remove
a non-primary address. The primary address SHALL NOT be removable.

#### Scenario: Adding and verifying an address

- **WHEN** the user adds an email address and enters the code sent to it
- **THEN** the address becomes verified and appears in the list as verified

#### Scenario: Wrong verification code

- **WHEN** the user submits an incorrect verification code
- **THEN** an error is shown, the address stays unverified, and the user can
  retry or request a new code

#### Scenario: Primary address is protected

- **WHEN** the user views the primary email address
- **THEN** no remove action is offered for it

### Requirement: Account security management

The Profile section SHALL let the user manage account security via Clerk: set or
change their password (requiring the current password when one exists, and
confirming the new one), review active sessions other than the current one with
device and last-active information and revoke any of them, and list connected
OAuth accounts with the ability to connect a new provider or disconnect an
existing one. Disconnecting the only remaining sign-in method SHALL be prevented.

#### Scenario: Password is changed

- **WHEN** the user submits a valid current password and a matching new password
- **THEN** the password is updated in Clerk and a success confirmation is shown

#### Scenario: Password confirmation mismatch

- **WHEN** the new password and its confirmation differ
- **THEN** the form shows a validation error and no request is sent

#### Scenario: Another session is revoked

- **WHEN** the user revokes a listed session
- **THEN** that session is ended in Clerk and disappears from the list, while the
  current session remains signed in

#### Scenario: Last sign-in method is protected

- **WHEN** disconnecting an OAuth account would leave the user with no password
  and no other connected account
- **THEN** the disconnect action is unavailable and the reason is explained

### Requirement: Application preferences

The Profile section SHALL expose the application preferences the app already
persists — at minimum the colour theme (light, dark, or system) — as an explicit
control, and changing a preference SHALL take effect immediately and survive a
reload.

#### Scenario: Theme is changed from settings

- **WHEN** the user selects a different theme in preferences
- **THEN** the interface switches to that theme immediately and the choice is
  still in effect after a reload

### Requirement: Organization profile editing

The Organization section SHALL display the organization's name, slug, status, and
creation date from `GET /api/v1/organization`, and SHALL let an authorized caller
update the name and slug via `PATCH /api/v1/organization`. Authorization SHALL
match the API: system admins and org `admin`s may edit; every other role sees the
same fields read-only with an explanation rather than a hidden or broken form.
The organization logo SHALL be editable through Clerk for the same roles.

#### Scenario: Admin updates the organization name

- **WHEN** an org admin changes the name and saves
- **THEN** `PATCH /api/v1/organization` is called, a success confirmation is
  shown, and the displayed profile reflects the new name

#### Scenario: Slug collision

- **WHEN** the API rejects the slug with 409 because it is already in use
- **THEN** the slug field shows that specific message and the form stays editable

#### Scenario: Non-admin sees a read-only profile

- **WHEN** a `member` or `viewer` opens the Organization section
- **THEN** the profile fields are visible but not editable, with a note that
  organization administration requires an admin role

### Requirement: Organization member management

The Organization section SHALL manage membership through Clerk's organization
APIs, which are authoritative for members and roles — the local `User` rows are
projections maintained by the Clerk webhook and SHALL NOT be written by this UI.
It SHALL list current members with name, email, avatar, and role; let an
authorized caller change a member's role or remove a member; and paginate or
scroll when the organization is large. A member whose local record does not yet
exist (invited but never signed in) SHALL still be listed.

#### Scenario: Members are listed

- **WHEN** an authorized user opens the Members panel
- **THEN** the organization's members are listed with their identity and role,
  sourced from Clerk

#### Scenario: A member's role is changed

- **WHEN** an admin selects a new role for a member and confirms
- **THEN** the role is updated in Clerk and the list reflects it

#### Scenario: A member is removed

- **WHEN** an admin removes a member and confirms the destructive action
- **THEN** the membership is deleted in Clerk and the member disappears from the
  list

#### Scenario: Self-demotion and last-admin removal are blocked

- **WHEN** an admin attempts to change their own role or to remove or demote the
  only remaining admin
- **THEN** the action is prevented in the UI with an explanation, so the
  organization cannot be left without an administrator

#### Scenario: Caller's own role changes

- **WHEN** an operation changes the signed-in user's own role or membership
- **THEN** `GET /users/me` is refetched so the app's principal, and every control
  gated on it, matches the new role

### Requirement: Organization invitations

The Organization section SHALL let an authorized caller invite a person by email
address with a chosen role, list pending invitations with their email, role, and
status, and revoke a pending invitation. Invitations SHALL be created through
Clerk.

#### Scenario: An invitation is sent

- **WHEN** an admin submits a valid email address and role
- **THEN** the invitation is created in Clerk, a confirmation is shown, and it
  appears in the pending list

#### Scenario: Duplicate or invalid invitation

- **WHEN** Clerk rejects the invitation (already a member, already invited, or a
  malformed address)
- **THEN** the returned reason is shown on the form and no pending entry is added

#### Scenario: A pending invitation is revoked

- **WHEN** an admin revokes a pending invitation
- **THEN** it is revoked in Clerk and removed from the pending list

### Requirement: Organization suspension danger zone

The Organization section SHALL offer suspension of the organization via
`DELETE /api/v1/organization` in a visually distinct danger zone, visible only to
system admins and org `admin`s. The action SHALL require an explicit confirmation
in which the user types the organization's name, and SHALL state plainly that it
is a soft-suspend that retains all data, blocks access until restored, and
propagates to Clerk.

#### Scenario: Suspension is confirmed

- **WHEN** an admin types the organization name and confirms
- **THEN** `DELETE /api/v1/organization` is called and the app moves the user to
  a state consistent with a suspended organization rather than leaving a stale
  authenticated view

#### Scenario: Confirmation text does not match

- **WHEN** the typed text does not exactly match the organization name
- **THEN** the confirm action stays disabled

#### Scenario: Danger zone is hidden from non-admins

- **WHEN** a `moderator`, `member`, or `viewer` opens the Organization section
- **THEN** the danger zone is not rendered

### Requirement: Company management

The Companies section SHALL list the organization's companies from
`GET /api/v1/companies`, including inactive ones behind an explicit toggle
(`include_inactive`), showing name, country, VAT number, and active state. An
authorized caller SHALL be able to create a company (`POST /api/v1/companies`),
edit its name, country code, and VAT number (`PATCH /api/v1/companies/{id}`), and
deactivate or reactivate it
(`POST /api/v1/companies/{id}/deactivate|activate`). Companies SHALL never be
presented as hard-deletable, matching the API's soft-deactivation model. After a
successful mutation the company list SHALL be refetched so the table reflects
server state.

#### Scenario: Companies are listed

- **WHEN** the Companies section loads
- **THEN** the organization's active companies are listed with their details

#### Scenario: Inactive companies are revealed

- **WHEN** the user enables the "show inactive" toggle
- **THEN** the list is refetched with `include_inactive=true` and deactivated
  companies appear, visibly marked as inactive

#### Scenario: A company is created

- **WHEN** an authorized user submits a new company with at least a name
- **THEN** `POST /api/v1/companies` is called, a confirmation is shown, and the
  new company appears in the list

#### Scenario: A company is edited

- **WHEN** an authorized user changes a company's details and saves
- **THEN** only the changed fields are sent as a partial update and the list
  reflects the result

#### Scenario: A company is deactivated and restored

- **WHEN** an authorized user deactivates a company and confirms, then later
  reactivates it
- **THEN** the corresponding endpoint is called each time and the company's
  active state in the list follows, with no delete action offered at any point

#### Scenario: Empty state

- **WHEN** the organization has no companies
- **THEN** an explicit empty state invites the user to create the first one,
  rather than showing a bare table

### Requirement: Role-based gating of settings controls

Every write control in the settings area SHALL be gated on the current
principal's role using the same rules the web API enforces — organization profile
and suspension require system admin or `admin`; company writes require system
admin, `admin`, or `moderator`; personal profile actions are always available to
the signed-in user. Unauthorized users SHALL see the data read-only with a stated
reason, not a hidden panel or a control that fails on submit. Client-side gating
is a usability affordance only, and SHALL NOT be relied on for enforcement.

#### Scenario: Read-only company management for a viewer

- **WHEN** a `viewer` opens the Companies section
- **THEN** the company list renders with no create, edit, or deactivate controls,
  and a note explains that changes require a management role

#### Scenario: Moderator may manage companies but not the organization

- **WHEN** a `moderator` opens the settings area
- **THEN** company write controls are available while organization profile
  editing and the danger zone are not

#### Scenario: Server rejection is still handled

- **WHEN** the API returns 403 for a write the UI believed was permitted
- **THEN** the rejection is surfaced as an error message and no local state is
  left claiming the change succeeded

### Requirement: Consistent save, feedback, and error behaviour

Settings forms SHALL share one interaction contract: a form is submittable only
when it is dirty and valid; the submit control shows a pending state and is
disabled while a mutation is in flight; success produces a toast or inline
confirmation; and failure surfaces the API's or Clerk's error message — mapped to
the offending field where the error identifies one — while leaving the user's
input intact for correction. Destructive actions SHALL require confirmation.
After a successful mutation the affected queries SHALL be invalidated so the UI
shows server state rather than assumed state.

#### Scenario: Pristine form cannot be submitted

- **WHEN** a settings form has no changes
- **THEN** its save control is disabled

#### Scenario: In-flight submission

- **WHEN** a save is in progress
- **THEN** the control shows a pending state and repeated submission is prevented

#### Scenario: Failure keeps user input

- **WHEN** a save fails
- **THEN** the error message is shown, the entered values are still present, and
  the form can be resubmitted

#### Scenario: Cache reflects the server after a change

- **WHEN** a mutation succeeds
- **THEN** the queries backing the changed data are invalidated and refetched
