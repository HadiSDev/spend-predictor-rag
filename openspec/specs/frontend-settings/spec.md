# frontend-settings Specification

## Purpose
TBD - created by syncing change settings-page. Update Purpose after archive.
## Requirements
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

Creating a company SHALL also connect its ERP system in the same dialog. The create form
SHALL include an ERP connection section offering the connector types from
`GET /api/v1/erp-types` and rendering an input per credential field that the chosen
connector declares, marking secret fields as password inputs and prefilling any declared
defaults. When exactly one connector type is available it SHALL be preselected. Submission
SHALL be blocked until the required connection fields are filled, and the company and its
integration SHALL be sent as one `POST /api/v1/companies` request.

Editing a company SHALL also expose its ERP connection, scoped to what the API supports on
an existing integration:

- The connector type SHALL be shown but SHALL NOT be changeable, since the API offers no
  way to change it.
- The integration's `label` SHALL be editable via `PATCH /api/v1/erp-integrations/{id}`.
- Credentials SHALL NOT be prefilled — the API never returns them. Replacing them SHALL be
  a deliberate act behind an explicit control, and SHALL make clear that **all** credential
  fields are replaced, since the API stores them as one map. Leaving that control untouched
  SHALL send no `credentials` and leave the stored secret unchanged.
- Whether credentials are currently stored SHALL be shown (from `has_credentials`), never
  their values.
- A company with **no** integration SHALL be offered the full connect form instead —
  connector picker and credential fields — submitting to `POST /api/v1/erp-integrations`,
  so a company created before this change can be connected.
- A company with **several** integrations SHALL edit its first connected one and SHALL say
  that the others exist rather than silently hiding them.

Company fields and integration fields SHALL be submitted as separate requests, since they
are separate resources; a failure of either SHALL be surfaced and SHALL NOT be reported as
success.

#### Scenario: Companies are listed

- **WHEN** the Companies section loads
- **THEN** the organization's active companies are listed with their details

#### Scenario: Inactive companies are revealed

- **WHEN** the user enables the "show inactive" toggle
- **THEN** the list is refetched with `include_inactive=true` and deactivated
  companies appear, visibly marked as inactive

#### Scenario: A company is created with its ERP connection

- **WHEN** an authorized user submits a new company with a name and the required ERP
  connection fields
- **THEN** a single `POST /api/v1/companies` carrying both the company fields and the
  `integration` block is called, a confirmation is shown, and the new company appears in
  the list

#### Scenario: The connector picker is data-driven

- **WHEN** the create dialog opens
- **THEN** the connector options and their credential inputs come from
  `GET /api/v1/erp-types`, and with only the debug connector registered it is the sole
  option and is preselected

#### Scenario: Missing connection details block submission

- **WHEN** an authorized user submits the create form with a name but a required
  credential field left empty
- **THEN** the field is marked invalid, no request is sent, and no company is created

#### Scenario: A company is edited

- **WHEN** an authorized user changes a company's details and saves without touching the
  ERP connection
- **THEN** only the changed company fields are sent as a partial update, no integration
  request is made, and the list reflects the result

#### Scenario: An integration's label is renamed

- **WHEN** an authorized user changes the integration's label in the edit dialog and saves
- **THEN** `PATCH /api/v1/erp-integrations/{id}` is called with the label alone and no
  `credentials` key, leaving the stored secret untouched

#### Scenario: Credentials are replaced deliberately

- **WHEN** an authorized user enables the replace-credentials control, fills every field,
  and saves
- **THEN** `PATCH /api/v1/erp-integrations/{id}` is called with the full credentials map,
  and the dialog states beforehand that all credentials are replaced

#### Scenario: Stored credentials are reported, never shown

- **WHEN** the edit dialog opens for an integration with `has_credentials: true`
- **THEN** it states that credentials are set, prefills no credential input, and displays
  no secret value

#### Scenario: A company with no integration can be connected

- **WHEN** an authorized user edits a company that has no integration
- **THEN** the full connect form is offered and submitting it calls
  `POST /api/v1/erp-integrations` for that company

#### Scenario: A failed integration update is not reported as success

- **WHEN** the company update succeeds but the integration request is rejected
- **THEN** the error is surfaced and the dialog does not claim the change succeeded

#### Scenario: A company is deactivated and restored

- **WHEN** an authorized user deactivates a company and confirms, then later
  reactivates it
- **THEN** the corresponding endpoint is called each time and the company's
  active state in the list follows, with no delete action offered at any point

#### Scenario: Empty state

- **WHEN** the organization has no companies
- **THEN** an explicit empty state invites the user to create the first one,
  rather than showing a bare table

### Requirement: A company's base currency is chosen in company settings

The company create form and the company edit form SHALL each offer a base
currency field, presented as a searchable list showing both code and name, so a
user picks `DKK — Danish Krone` rather than typing a code. The list SHALL be the
currencies daily reference rates are published for, which is exactly the set the
system can convert into.

- On the create form the field SHALL be required and SHALL be submitted with the
  company; the form SHALL NOT submit without it.
- The field SHALL default to the currency implied by the selected country when
  one is known, as a pre-selection the user can change — never as a silent
  choice made on their behalf.
- The company list SHALL show each company's base currency, so a user managing
  several companies can see which currency each reports in.
- The field SHALL follow the same role gating and the same save/feedback/error
  behaviour as the other company fields.

#### Scenario: Creating a company requires a currency

- **WHEN** a user opens the create-company form and submits without choosing a
  base currency
- **THEN** the form reports the missing field and no request is sent

#### Scenario: The country pre-selects a currency

- **WHEN** the user selects Denmark as the country
- **THEN** `DKK` is pre-selected and remains freely changeable

#### Scenario: A viewer cannot change it

- **WHEN** a user without management rights opens company settings
- **THEN** the base currency is shown read-only, consistent with the other
  company fields

### Requirement: Changing the base currency prompts a recompute

When a user changes an existing company's base currency, the UI SHALL explain
that already-imported figures are still stored in the previous currency and
SHALL offer to recompute them, calling the recompute endpoint and reporting its
result.

- The explanation SHALL appear immediately on saving the change, on the same
  screen — not later, after the user has navigated away.
- While a recompute is running the control SHALL show progress and SHALL NOT be
  re-triggerable.
- The result SHALL be reported as counts of converted and still-unconverted rows,
  and a failure SHALL be surfaced with the same error treatment as other settings
  actions.
- Declining the recompute SHALL still leave the currency change saved; the user
  SHALL be able to trigger the recompute later from the same screen.

#### Scenario: Recompute is offered on change

- **WHEN** a manager changes a company's base currency from `DKK` to `EUR` and
  confirms
- **THEN** the change is saved and the UI offers to recompute the company's
  stored figures

#### Scenario: Recompute reports what it did

- **WHEN** the user runs the recompute
- **THEN** progress is shown and the finished run reports how many rows were
  converted and how many remain unconverted

#### Scenario: Declining leaves the change in place

- **WHEN** the user declines the recompute
- **THEN** the new base currency is still saved and the recompute remains
  available from the company's settings

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

### Requirement: ERP account selection for a company

The settings area SHALL provide `/settings/companies/$companyId/accounts`, listing the company's ERP chart of accounts from `GET /api/v1/erp-integrations/{id}/accounts` with each account's code, name, type, and its two customer-owned settings — **Sync** (`sync_enabled`) and **VAT** (`with_vat`) — each toggleable via `PATCH /api/v1/erp-accounts/{id}`.

- The page SHALL be reached from the company row's action menu, and that entry
  SHALL be disabled for a company with no connected integration, since there is
  no chart to manage.
- Each toggle SHALL save on its own, immediately, without a form or a save
  button. A chart is reviewed by scanning and flipping a few switches; batching
  the changes makes a partial failure impossible to attribute.
- A failed toggle SHALL revert the switch and surface the error against that
  account, so the page never shows a setting that did not persist.
- The page SHALL explain what each toggle does: turning Sync off stops future
  ingestion and does **not** remove entries already synced, and the VAT flag
  records an assumption used when reconciling parsed invoices against posted
  entries rather than recomputing any stored amount.

#### Scenario: Accounts are listed with their settings

- **WHEN** a manager opens a connected company's accounts page
- **THEN** its ERP accounts are listed with code, name, type, and the current
  state of both toggles

#### Scenario: A toggle saves on its own

- **WHEN** a manager flips one account's Sync switch
- **THEN** only that account is patched, and the row reflects the server's result

#### Scenario: A failed toggle does not lie

- **WHEN** a toggle's request fails
- **THEN** the switch returns to its previous state and the error is shown against
  that account

#### Scenario: The action is unavailable without an integration

- **WHEN** a company has no connected ERP integration
- **THEN** the "manage accounts" entry in its action menu is disabled

### Requirement: Account list is searchable with scoped bulk actions

The accounts page SHALL provide a search over account code and name, and bulk enable/disable actions that apply **only to the accounts currently shown**.

- A bulk action SHALL state how many accounts it will affect before it is
  performed, so a filtered view cannot be mistaken for the whole chart.
- A bulk action SHALL NOT act on accounts hidden by the current search.
- The page SHALL show how many accounts exist and how many are sync-enabled.

#### Scenario: Search narrows the list

- **WHEN** a manager types part of an account code or name
- **THEN** only matching accounts are listed

#### Scenario: A bulk action is scoped to what is visible

- **WHEN** a search is active and the manager uses "disable all"
- **THEN** only the accounts matching that search are patched, and the control
  states that count beforehand

### Requirement: The account chart can be refreshed from the ERP

The accounts page SHALL offer a refresh action calling `POST /api/v1/erp-integrations/{id}/refresh-accounts`, and SHALL report what the refresh found.

- The result SHALL state how many accounts were seen and how many were newly
  added, rather than silently refetching.
- An integration whose chart has never been fetched SHALL show an empty state
  offering the refresh, not an empty table.

#### Scenario: A refresh reports what it found

- **WHEN** a manager refreshes the chart
- **THEN** the number of accounts seen and added is reported and the list updates

#### Scenario: An unfetched chart invites a refresh

- **WHEN** a company's integration has no accounts yet
- **THEN** an empty state explains this and offers to refresh from the ERP

### Requirement: Account settings are read-only without management rights

A principal without management rights SHALL see the account chart and both settings, with every control that writes disabled and the reason stated — matching that `GET .../accounts` requires only tenant scope while `PATCH /erp-accounts/{id}` and `refresh-accounts` require management.

#### Scenario: A viewer sees the chart but cannot change it

- **WHEN** a `member` or `viewer` opens the accounts page
- **THEN** the accounts and their settings are visible, and the toggles, bulk
  actions, and refresh control are disabled with the reason stated

### Requirement: The ERP connector chooser is a branded card grid

The connector chooser in the company create and connect forms SHALL present each
connector as a card carrying its mark, its label and a one-line description,
rather than as a list of text options — choosing an ERP system is the moment a
user decides whether this product supports their accounting system.

- The grid SHALL be rendered entirely from `GET /api/v1/erp-types`. The
  front-end SHALL NOT contain a list of connector names, a per-connector branch,
  or brand text of its own; a connector registered later SHALL appear with no
  front-end change.
- A card SHALL show its connector's mark, resolved from the catalog's
  `brand_slug` against artwork vendored in the repository. Artwork SHALL NOT be
  loaded from a third-party host.
- A connector whose artwork is absent SHALL fall back to a lettered tile of the
  same size and shape. The fallback SHALL look deliberate rather than broken,
  because it is the normal state for every connector we have not drawn.
- The catalog's `description` SHALL be shown on the card when present, and the
  card SHALL omit the line rather than substituting invented text when absent.
- Selection SHALL be visibly distinct from hover and SHALL be keyboard operable
  and screen-reader labelled, since it replaces a native control.
- Choosing a connector SHALL reseed the credential inputs below from that
  connector's declared defaults, as the previous control did.
- When exactly one connector is available it SHALL still be preselected.
- The credential inputs, the edit-mode behaviour, and the fixed-once-connected
  rule for `erp_type` SHALL be unchanged: this requirement governs the chooser
  only.

#### Scenario: Connectors are presented as branded cards

- **WHEN** the company create dialog opens
- **THEN** one card per connector from `GET /api/v1/erp-types` is shown, each
  with its mark, its label, and its description when the catalog supplies one

#### Scenario: A connector with no artwork still reads as a card

- **WHEN** the catalog returns a connector whose `brand_slug` has no vendored
  artwork, or no `brand_slug` at all
- **THEN** its card shows a lettered tile in place of the mark and is otherwise
  identical to the others

#### Scenario: Choosing a card reseeds the credential fields

- **WHEN** the user selects the Billy card
- **THEN** the credential inputs below are replaced by Billy's declared fields,
  prefilled with their declared defaults, with secret fields as password inputs

#### Scenario: The grid is keyboard operable

- **WHEN** the user moves through the chooser with the keyboard and selects a
  connector
- **THEN** the selection changes, the selected card is announced as selected,
  and the form behaves as if it had been clicked

#### Scenario: No connector name is hardcoded in the front-end

- **WHEN** the catalog returns a connector the front-end has never seen
- **THEN** it is rendered as a card with the same treatment as the others,
  requiring no front-end change

#### Scenario: Submitting still sends one company request

- **WHEN** the user picks a connector from the grid, fills its credentials, and
  submits the create form
- **THEN** a single `POST /api/v1/companies` carrying the company fields and the
  `integration` block is sent, exactly as before

### Requirement: Spend trees are managed in Settings

Settings SHALL carry a **Spend trees** section, reachable at `/settings/spend-trees` and linked from the settings navigation like the other sections. It SHALL list the organization's trees, each showing its name, depth (`3 levels` / `4 levels`), whether it is the default-template copy or a custom tree, its node count, and the companies assigned to it.

The section SHALL be readable by any authenticated member and SHALL gate every mutating control behind the management role, using the same disabled-with-explanation treatment the rest of Settings uses.

#### Scenario: The organization's trees are listed

- **WHEN** a member opens `/settings/spend-trees`
- **THEN** each of the organization's trees is listed with its depth, source, node count, and assigned companies

#### Scenario: A viewer sees but cannot change

- **WHEN** a `viewer` opens the section
- **THEN** the trees are readable and every create, edit, import, and assign control is unavailable with the reason shown

#### Scenario: The default tree is obtainable from the section

- **WHEN** the organization holds no default-template tree
- **THEN** the section offers to add it, and taking that offer creates the organization's copy and lists it

#### Scenario: The offer disappears once taken

- **WHEN** the organization already holds a default-template copy
- **THEN** the section does not offer to add one

#### Scenario: Loading, empty, and error states

- **WHEN** the tree list is loading, returns nothing, or fails
- **THEN** the section shows the loading, empty, or error state rather than an ambiguous blank panel

### Requirement: A tree can be archived or deleted from its row

Each tree row SHALL offer, to a manager only, **Archive** and **Delete**. Deleting SHALL confirm first, and SHALL surface the server's refusal rather than a generic failure: a tree still assigned to a company names those companies and is not retryable by confirming, while a tree that categorized lines point at reports the count and SHALL be retryable with an explicit "delete anyway".

#### Scenario: Deleting an unused tree

- **WHEN** a manager deletes a tree nothing uses and confirms
- **THEN** the tree is removed from the list

#### Scenario: A tree in use explains itself

- **WHEN** the delete is refused because a company is assigned
- **THEN** the dialog names the companies and offers no way to force it

#### Scenario: Orphaning lines is a decision, not a wall

- **WHEN** the delete is refused because three lines are categorized against the tree
- **THEN** the dialog reports the three lines and offers to delete anyway, which succeeds

#### Scenario: A read-only member gets no row actions

- **WHEN** a `member` or `viewer` views the list
- **THEN** no archive or delete control is offered

### Requirement: A tree is created by cloning, from scratch, or by CSV import

The create flow SHALL offer three starting points in one dialog: **clone an existing tree**, **start empty**, and **import a CSV**. Cloning SHALL default to the organization's default-template copy. The dialog SHALL let the caller name the tree and choose a maximum depth of 3 or 4, with 4 unavailable when cloning the default-template copy is not the chosen path only insofar as the server rejects it — the client SHALL surface the server's reason rather than inventing its own rule.

CSV import SHALL show the file's parsed row count before applying, and on rejection SHALL show the offending rows with their line numbers rather than a single opaque failure. A rejected import SHALL leave the tree visibly unchanged.

#### Scenario: Cloning the default

- **WHEN** a manager creates a tree choosing "clone" with the default-template copy as the source
- **THEN** a new custom tree appears in the list with the same node count, and editing it does not change the source tree

#### Scenario: Import errors are actionable

- **WHEN** an imported CSV has three invalid rows
- **THEN** the dialog names each offending row with its line number and reason, and the tree's node count is unchanged

#### Scenario: A replace import warns first

- **WHEN** a replace import would remove nodes that categorized lines reference
- **THEN** the dialog reports how many lines are affected and requires an explicit confirmation before applying

### Requirement: A tree's nodes are edited as a tree

Opening a tree SHALL show its nodes as an expandable hierarchy, not a flat table of level columns. A manager SHALL be able to add a child under any node, rename a node, reorder siblings, edit a node's description and code, and delete a node.

The editor SHALL make depth legible: adding a child under a node already at the tree's maximum depth SHALL be unavailable, with the reason stated, rather than offered and then rejected by the server. Deleting a node with children SHALL be refused with its child count shown. Deleting a node that categorized lines reference SHALL state how many lines will lose their category pointer before it is confirmed.

#### Scenario: Adding a child

- **WHEN** a manager adds a child under a level-2 node of a 4-level tree
- **THEN** the node appears at level 3 under that parent and the tree's node count increases by one

#### Scenario: Depth limit is visible before it bites

- **WHEN** a manager views a node at the tree's maximum depth
- **THEN** the add-child control is unavailable and states that the tree's maximum depth has been reached

#### Scenario: Deleting a referenced node is confirmed

- **WHEN** a manager deletes a node that 12 invoice lines reference
- **THEN** the confirmation states that 12 lines will lose their category assignment, and cancelling changes nothing

### Requirement: A company's tree is chosen in company settings

Company settings SHALL let a manager choose which spend tree the company categorizes against, from the organization's active trees. When the organization holds no default-template copy, the picker SHALL additionally offer the default — choosing it creates and assigns the copy — because a company that predates spend trees has no tree and creating a new company is not a reasonable way to obtain one. The option SHALL disappear once the copy exists, where it would duplicate the entry already listed by name. The current tree SHALL be shown wherever the company's other categorization-relevant settings are shown.

Changing the assignment SHALL warn before saving that already-categorized lines whose category is not in the new tree will be marked for review, and SHALL make clear that no categorization values are deleted. After saving, the outcome SHALL be reported with the exact number of affected lines and a link to them.

The count is stated **after** the save, not before it: it exists only server-side, and there is no dry-run endpoint. Reporting the exact number the moment it is known is preferable to estimating it beforehand — a wrong number in a confirmation is worse than no number.

#### Scenario: Choosing a different tree

- **WHEN** a manager changes a company's spend tree
- **THEN** the form states that lines whose category is not in the new tree will need reviewing, and that their existing categories are kept

#### Scenario: The outcome is reachable

- **WHEN** the reassignment completes
- **THEN** the result reports the affected line count and links to the entries view filtered to those lines

#### Scenario: Only the organization's trees are offered

- **WHEN** the tree picker opens
- **THEN** it lists only the caller's organization's active trees

### Requirement: A system admin can delete a company from Settings

The companies list SHALL offer a delete action on each company row, shown only to
a system admin, alongside the existing deactivate action.

- A reader without the platform flag SHALL NOT see the action at all, rather than
  see it disabled. A disabled control claims a permission that will never be
  granted.
- Activating it SHALL open a confirmation naming the company and stating what
  would be destroyed — invoices, lines, postings — and that the action cannot be
  undone.
- The confirmation SHALL require typing the company's name to arm it. This is the
  only action in the product with no undo, so it is the only one that asks for
  more than a click: a checkbox is a reflex, a name is a second look at *which*
  company.
- The dialog SHALL point at deactivation as the reversible alternative, since a
  reader who wanted that and reached for this cannot tell the difference from the
  labels alone.
- A server refusal SHALL be shown in the dialog rather than dismissing it, so the
  counts arrive where the decision is being made.

#### Scenario: The action is offered to a system admin

- **WHEN** a system admin views the companies list
- **THEN** each company row offers a delete action

#### Scenario: It is absent for everyone else

- **WHEN** an org admin, moderator, member or viewer views the list
- **THEN** no delete action is rendered, disabled or otherwise

#### Scenario: The confirmation states the consequence

- **WHEN** a system admin activates the action for a company holding records
- **THEN** the dialog names the company, states what would be destroyed, and says
  the action cannot be undone

#### Scenario: The name arms the confirmation

- **WHEN** the dialog is open and the company's name has not been typed
- **THEN** the confirming control is disabled, and typing the name enables it

#### Scenario: Deactivation is offered as the reversible option

- **WHEN** the dialog is open
- **THEN** it names deactivation as the alternative that keeps the records

#### Scenario: A refusal is shown where the decision is made

- **WHEN** the server refuses the deletion
- **THEN** the dialog stays open showing the reason

### Requirement: Failed lines can be requeued from the company row menu

The Companies section's row menu SHALL offer a **Recategorize failed lines** action,
alongside *Recompute currency figures*, calling
`POST /api/v1/companies/{id}/recategorize`.

The two actions are deliberately siblings: both are company-scoped maintenance a customer
runs after something upstream changed, both report a count rather than changing what is on
screen, and both are management-gated.

- The action SHALL be hidden or disabled for a caller without management rights, following
  the section's existing role gating. A control that is present but will always fail claims
  a permission that will never be granted.
- The action SHALL confirm before running, stating that it queues lines rather than
  categorizing them, and SHALL report the number queued when it completes.
- The action SHALL surface a failure as a failure, and SHALL NOT report success when the
  request fails — the section's existing save-and-feedback rule.

#### Scenario: The action is offered

- **WHEN** a management user opens a company's row menu
- **THEN** a "Recategorize failed lines" action is offered

#### Scenario: A read-only user is not offered it

- **WHEN** a user without management rights opens a company's row menu
- **THEN** the action is absent or disabled

#### Scenario: The confirmation says what will happen

- **WHEN** the user activates the action
- **THEN** they are asked to confirm, and told that the lines are queued for the next sync
  rather than categorized now

#### Scenario: The result reports the count

- **WHEN** the request succeeds
- **THEN** the number of lines queued is reported to the user

#### Scenario: Nothing to requeue is stated plainly

- **WHEN** the request succeeds with a queued count of zero
- **THEN** the user is told no failed lines were found, not that work was done

#### Scenario: A failure is not reported as success

- **WHEN** the request fails
- **THEN** the error is surfaced and no success message is shown

### Requirement: A tree's suggested categories SHALL be reviewable where the tree is edited

The spend-tree editor in Settings SHALL surface the pending gap suggestions for the tree being edited, each showing the proposed name, the parent it would be added under, the reason given, and the lines that evidence it.

They belong beside the tree rather than in a notifications area because accepting one is a tree edit: the reviewer needs the tree in front of them to judge whether the proposal duplicates a node they already have, and to see where it would land.

#### Scenario: Suggestions appear with the tree

- **WHEN** a manager opens a tree that has pending suggestions
- **THEN** the suggestions are visible alongside its nodes, each naming its proposed parent

#### Scenario: The evidence is reachable

- **WHEN** a manager opens a suggestion
- **THEN** the lines that evidence it are listed and each links to that line

#### Scenario: A tree with no suggestions shows no empty apparatus

- **WHEN** a tree has no pending suggestions
- **THEN** the editor shows the tree as it does today, with no empty suggestions panel

### Requirement: Accepting a suggestion SHALL show its result in the tree, and dismissing SHALL be undoable in the same session

Accepting a suggestion SHALL create the node and show it in the tree immediately, in the position it was proposed for, so the reviewer sees the consequence where they caused it. Dismissing SHALL remove the suggestion from the list and SHALL offer an undo for the remainder of that session.

Accept and dismiss SHALL be available only to a role that may edit the tree. A read-only role SHALL see the suggestions as evidence and SHALL NOT be shown disabled accept controls, which claim a permission that will never be granted.

#### Scenario: An accepted suggestion becomes a visible node

- **WHEN** a manager accepts a suggestion
- **THEN** the new node appears under the named parent in the tree without a reload

#### Scenario: A dismissal can be taken back

- **WHEN** a manager dismisses a suggestion
- **THEN** an undo is offered and taking it restores the suggestion to the pending list

#### Scenario: A viewer sees evidence, not controls

- **WHEN** a `viewer` opens a tree with pending suggestions
- **THEN** the suggestions and their evidence are readable and no accept or dismiss control is rendered

