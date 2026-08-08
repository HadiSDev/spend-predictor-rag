## 1. Foundations — mutating API client

- [x] 1.1 Extend `frontend/src/lib/api-client.ts`: refactor the private `request`
  to take a method and optional JSON body, set `Content-Type: application/json`
  only when a body is present, and resolve `204` without parsing a body.
- [x] 1.2 Add `post`, `patch`, and `del` to the `ApiClient` interface and its
  implementation, keeping `get`'s existing signature untouched.
- [x] 1.3 Give `ApiError` a `detail` accessor that extracts FastAPI's
  `{"detail": "..."}` and the 422 `detail: [{msg, loc}]` array shape from the
  parsed body, falling back to the current generic message.
- [x] 1.4 Add `frontend/src/lib/api-client.test.ts` covering: a POST sends the
  JSON body and the bearer token; a 409 with a `detail` string exposes it via
  `ApiError.detail`; a 204 resolves without throwing.

## 2. Foundations — role gating and types

- [x] 2.1 Add `canManageOrganization(principal)` and
  `canManageCompanies(principal)` to `frontend/src/lib/auth.tsx`, mirroring
  `require_org_admin` / `require_management` in `src/web_api/deps.py`, with a
  comment in each file pointing at the other.
- [x] 2.2 Add `OrganizationRead`, `OrganizationUpdate`, `CompanyRead`,
  `CompanyCreate`, and `CompanyUpdate` to `frontend/src/lib/types.ts`, mirroring
  `src/web_api/schemas.py`.
- [x] 2.3 Add `frontend/src/lib/auth.test.ts` asserting the gating helpers for
  each role plus the system-admin override.

## 3. Foundations — resource modules

- [x] 3.1 Create `frontend/src/lib/organization.ts` with
  `organizationQueryOptions(api)` (key `['organization']`),
  `updateOrganizationMutation(api, qc)`, and `suspendOrganizationMutation(api, qc)`,
  invalidating `['organization']` and `['users','me']` on success.
- [x] 3.2 Create `frontend/src/lib/companies.ts` with
  `companiesQueryOptions(api, { includeInactive })` (key
  `['companies', { includeInactive }]`) plus create, update, deactivate, and
  activate mutations that invalidate the `['companies']` prefix.

## 4. Shared application shell

- [x] 4.1 Extract `DashboardShell` from `frontend/src/routes/_authed/index.tsx`
  into `frontend/src/components/app-shell.tsx`, moving `UserMenu`, the sidebar,
  and the topbar unchanged; make the topbar title a prop or context so each route
  can set it.
- [x] 4.2 Render the shell in `frontend/src/routes/_authed.tsx` around
  `<Outlet />` so it mounts once, and reduce `_authed/index.tsx` to the dashboard
  content.
- [x] 4.3 Turn sidebar entries into router `<Link>`s using
  `sidebarNavItemClass(active)` with active state from the router; enable
  **Settings**, keep Invoices and Vendors disabled as non-links.
- [x] 4.4 Add a test asserting the sidebar renders Settings as an enabled link
  and marks the entry matching the current route as active.

## 5. Suspended-organization handling

- [x] 5.1 In `frontend/src/lib/auth.tsx`, detect a 403 `ApiError` whose detail is
  the suspended-organization message from `GET /users/me` and render a dedicated
  "Organization suspended" screen with a sign-out action, instead of the generic
  account-error fallback.
- [x] 5.2 Add a test that `AuthProvider` renders the suspended screen for that
  error and the generic screen for any other failure.

## 6. Settings route skeleton

- [x] 6.1 Create `frontend/src/routes/_authed/settings.tsx` as a layout route: the
  page header, the tab bar, and `<Outlet />`.
- [x] 6.2 Build the tab bar from the existing `Tabs`/`TabsList`/`TabsTab`, with
  each tab rendering a router `<Link>` via the `render` prop and `Tabs` `value`
  derived from the matched route (not local state).
- [x] 6.3 Create `_authed/settings/index.tsx` redirecting to
  `/settings/profile`, plus empty `profile.tsx`, `organization.tsx`, and
  `companies.tsx` section routes.
- [x] 6.4 Regenerate `routeTree.gen.ts` (`pnpm generate-routes`) and verify
  `/settings`, each section URL, deep-linking, and browser back all resolve to
  the right tab.

## 7. Profile section — identity and preferences

- [x] 7.1 Build `components/settings/profile-panel.tsx`: a presentational
  first-name / last-name form plus avatar upload and remove, taking current
  values, a submit handler, and pending/error state as props.
- [x] 7.2 Wire it in `settings/profile.tsx` to Clerk's `useUser` —
  `user.update()` and `user.setProfileImage()` — validating image type and size
  before upload and surfacing Clerk's error verbatim.
- [x] 7.3 Add a preferences card exposing the theme (light / dark / system) via
  the existing `useTheme`, taking effect immediately and persisting across reload.
- [x] 7.4 Confirm the topbar user menu reflects a saved name or avatar without a
  reload.
- [x] 7.5 Test the panel with props: dirty-gating on submit, pending state, and an
  error message rendering while entered values are preserved.

## 8. Profile section — email addresses

- [x] 8.1 Build the email list: each address with verified and primary badges,
  and actions to set primary or remove — never a remove action on the primary.
- [x] 8.2 Implement add-address with Clerk's verification-code flow
  (`createEmailAddress` → `prepareVerification` → `attemptVerification`),
  including a resend action.
- [x] 8.3 Surface an incorrect code as a retryable error that leaves the address
  unverified.
- [x] 8.4 Test the list rendering (badges, no remove on primary) and the wrong-code
  error path with mocked handlers.

## 9. Profile section — account security

- [x] 9.1 Build the password form: current password (only when one is set), new
  password, and confirmation, with a client-side mismatch error that sends no
  request; wire to Clerk's `user.updatePassword()`.
- [x] 9.2 Build the active-sessions list from Clerk's sessions with device and
  last-active info, excluding the current session, each revocable.
- [x] 9.3 Build the connected-accounts list with connect and disconnect, disabling
  disconnect (with a stated reason) when it would remove the last sign-in method.
- [x] 9.4 Test the mismatch validation, the last-sign-in-method guard, and that
  revoking a session removes it from the list.

## 10. Organization section — profile

- [x] 10.1 Build `components/settings/organization-panel.tsx`: name and slug form
  plus read-only status and creation date, with a `readOnly` mode.
- [x] 10.2 Wire `settings/organization.tsx` to `organizationQueryOptions` and
  `updateOrganizationMutation`, gated on `canManageOrganization`; non-admins get
  the read-only mode with a stated reason.
- [x] 10.3 Map a 409 response onto the `slug` field via `setError` using
  `ApiError.detail`, keeping the form editable.
- [x] 10.4 Add organization logo upload through Clerk for the same roles.
- [x] 10.5 Test: admin sees editable fields, `member` sees read-only with the
  reason, and a 409 renders on the slug field.

## 11. Organization section — members and invitations

- [x] 11.1 Build `components/settings/members-panel.tsx`: member list with avatar,
  name, email, and role, plus a pending-invitations list — presentational, driven
  by props and callbacks.
- [x] 11.2 Wire `useOrganization({ memberships: true, invitations: true })` for
  data and pagination; do not read `GET /api/v1/users`.
- [x] 11.3 Implement role change and member removal (`updateMember`,
  `removeMember` / `destroy`), each behind a confirmation for the destructive case.
- [x] 11.4 Block self-role-change and removing or demoting the last admin in the
  UI, with an explanation rather than a silently disabled control.
- [x] 11.5 Implement invite-by-email with a role selected from Clerk's allowed
  roles (not hard-coded), pending-invitation listing, and revoke; surface Clerk's
  rejection (already a member, already invited, malformed address) on the form.
- [x] 11.6 Invalidate `['users','me']` after any operation that can change the
  signed-in user's own role or membership.
- [x] 11.7 Test the panel with props: the last-admin and self-demotion guards, the
  invite error path, and that a revoked invitation leaves the pending list.

## 12. Organization section — danger zone

- [x] 12.1 Build the danger zone card, rendered only when
  `canManageOrganization` — copy stating that suspension retains all data, blocks
  access until restored, and propagates to Clerk.
- [x] 12.2 Implement typed-name confirmation in an `AlertDialog`, with confirm
  disabled until the text matches the organization name exactly.
- [x] 12.3 On confirm, call `suspendOrganizationMutation` and clear the query
  cache so the app converges on the suspended screen from task 5.1.
- [x] 12.4 Test: hidden for `moderator`/`member`/`viewer`; confirm stays disabled
  on mismatched text and enables on an exact match.

## 13. Companies section

- [x] 13.1 Build `components/settings/companies-panel.tsx`: a table of name,
  country, VAT, and active state with an explicit "show inactive" toggle, an
  empty state inviting the first company, and a `readOnly` mode.
- [x] 13.2 Wire `settings/companies.tsx` to `companiesQueryOptions`, passing
  `include_inactive` from the toggle so it refetches under its own query key.
- [x] 13.3 Implement create in a dialog form (name required; country and VAT
  optional) via `createCompanyMutation`.
- [x] 13.4 Implement edit in the same dialog form, sending only changed fields as
  a partial update.
- [x] 13.5 Implement deactivate and reactivate behind a confirmation, with no
  delete action offered anywhere in the UI.
- [x] 13.6 Gate every write control on `canManageCompanies`; `member`/`viewer`
  get the read-only table with a stated reason.
- [x] 13.7 Test: the empty state, inactive rows marked when revealed, absence of
  write controls for a `viewer`, and partial-update payload on edit.

## 14. Shared form and feedback conventions

- [x] 14.1 Factor the shared submit contract into one place — disabled while
  pristine or submitting, pending indicator, success toast via `useToast` — and
  use it in every settings form.
- [x] 14.2 Factor server-error mapping into one helper: `ApiError.detail` and
  Clerk's `meta.paramName` onto field errors via `setError`, otherwise a
  form-level error plus a toast.
- [x] 14.3 Verify a 403 on any write surfaces as an error and leaves no local
  state claiming success.

## 15. Verification

- [x] 15.1 Run `pnpm test`, `pnpm lint`, and `pnpm check` in `frontend/` and fix
  what they report.
- [ ] 15.2 Walk the app against a running web API: each tab deep-links and
  reloads correctly; org rename, invite, role change, company create/edit/
  deactivate all persist and refetch; error states render for a forced 403.
- [ ] 15.3 Check both light and dark themes, and keyboard navigation through the
  tabs, dialogs, and forms.
- [x] 15.4 Confirm no backend file changed and no new dependency was added.
