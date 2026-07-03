## ADDED Requirements

### Requirement: Signed webhook receiver

The API SHALL expose `POST /api/v1/webhooks/clerk` to receive Clerk (Svix) webhook events. It SHALL verify the Svix signature headers (`svix-id`, `svix-timestamp`, `svix-signature`) against the configured signing secret before processing, and reject unverified requests with `400`/`401`. The endpoint is unauthenticated (no Clerk session JWT) — the signature is the authentication.

#### Scenario: Valid signature is accepted

- **WHEN** a request arrives with a body and Svix headers that verify against the signing secret
- **THEN** the event is processed and the API responds `2xx`

#### Scenario: Invalid or missing signature is rejected

- **WHEN** the signature headers are missing or do not verify
- **THEN** the API responds with a 4xx error and applies no change

### Requirement: Idempotent event processing

Each webhook event SHALL be applied at most once. The receiver SHALL record every accepted event keyed by its Svix message id in a `WebhookEvent` record; a redelivered event with an id already processed SHALL be acknowledged (`2xx`) without re-applying its effect.

#### Scenario: Redelivered event is a no-op

- **WHEN** Clerk redelivers an event whose id was already processed
- **THEN** the API responds `2xx` and the domain is unchanged (no duplicate rows, no repeated side effects)

#### Scenario: Every event is auditable

- **WHEN** an event is received
- **THEN** a `WebhookEvent` row captures its id, type, payload, and processing outcome

### Requirement: Organization lifecycle events

The receiver SHALL apply organization events: `organization.created` provisions (find-or-create) the `Organization` linked by `clerk_org_id`; `organization.updated` syncs `name` and `slug`; `organization.deleted` soft-suspends the organization (`status='suspended'`, `suspended_at` set) and SHALL NOT delete the organization or its companies, invoices, or lines.

#### Scenario: Created provisions eagerly

- **WHEN** an `organization.created` event is processed
- **THEN** a matching `Organization` exists immediately, before any member's first API call

#### Scenario: Deleted soft-suspends and retains data

- **WHEN** an `organization.deleted` event is processed for an org with companies and invoices
- **THEN** the organization's `status` is `suspended` with `suspended_at` set, and all companies/invoices/lines remain intact

### Requirement: Suspended organizations block access

While an organization's `status` is `suspended`, its members SHALL NOT be able to read or manage its data through the API; such requests SHALL fail (e.g. `403`). Reactivation (a later `organization.created`/restore or an explicit reactivate) SHALL restore access.

#### Scenario: Suspended org member is denied

- **WHEN** a member of a suspended organization calls any tenant-scoped endpoint
- **THEN** the API denies the request while the organization remains suspended

### Requirement: Membership and user events

The receiver SHALL apply membership and user events: `organizationMembership.created`/`.updated` upserts the `User` and maps its org role; `organizationMembership.deleted` revokes that user's access to the organization; `user.updated` syncs the user's name/email; `user.deleted` revokes the user's access. Revoking access SHALL preserve referential integrity (records that reference the user are not orphaned into an invalid state).

#### Scenario: Membership role update is reflected

- **WHEN** an `organizationMembership.updated` event changes a member's role to `moderator`
- **THEN** the corresponding `User.role` becomes `moderator`

#### Scenario: Membership removal revokes access

- **WHEN** an `organizationMembership.deleted` event is processed for a user
- **THEN** that user can no longer access the organization's data via the API
