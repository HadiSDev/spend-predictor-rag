## ADDED Requirements

### Requirement: Propagate local organization suspension/deletion to Clerk

When an organization is suspended or deleted through our API, the system SHALL propagate the deletion to Clerk by calling the Clerk Backend API to delete the corresponding Clerk organization (identified by `clerk_org_id`). Propagation SHALL only occur for organizations that have a `clerk_org_id`. Outbound calls SHALL use the configured Clerk secret key and MAY be disabled by configuration (dev/tests).

#### Scenario: Local suspension deletes the Clerk org

- **WHEN** an authorized caller suspends/deletes an organization that has a `clerk_org_id`
- **THEN** the system calls the Clerk Backend API to delete that Clerk organization

#### Scenario: Synthetic org without Clerk linkage is skipped

- **WHEN** an organization without a `clerk_org_id` is suspended
- **THEN** no Clerk Backend API call is made and the local suspension still succeeds

#### Scenario: Outbound disabled in dev/test

- **WHEN** outbound propagation is disabled by configuration
- **THEN** local suspension succeeds and no Clerk call is attempted

### Requirement: Delete/suspend organization action

The API SHALL provide `DELETE /api/v1/organization` (system admin or org `admin`) that soft-suspends the caller's organization (`status='suspended'`, `suspended_at` set), retaining all data, and triggers outbound propagation to Clerk.

#### Scenario: Admin suspends their organization

- **WHEN** an org `admin` calls `DELETE /api/v1/organization`
- **THEN** the organization is soft-suspended, its data retained, and the Clerk org deletion is propagated

#### Scenario: Non-admin cannot suspend the organization

- **WHEN** a `moderator`, `member`, or `viewer` calls `DELETE /api/v1/organization`
- **THEN** the API responds `403 Forbidden` and no change is made

### Requirement: Echo-loop prevention

A change that originates locally and is propagated to Clerk SHALL NOT cause a duplicate or conflicting local change when Clerk echoes it back as a webhook. Applying the echoed event SHALL be a no-op because the local state already matches (idempotent handlers) — for example, an `organization.deleted` webhook for an already-suspended organization changes nothing.

#### Scenario: Echoed deletion is a no-op

- **WHEN** we suspend an organization, propagate the deletion to Clerk, and Clerk then delivers the `organization.deleted` webhook
- **THEN** processing that webhook leaves the already-suspended organization unchanged
