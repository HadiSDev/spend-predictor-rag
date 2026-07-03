## ADDED Requirements

### Requirement: Webhook event record

The domain SHALL include a `WebhookEvent` entity that records inbound provider webhooks for idempotency and audit. It SHALL carry a `provider` (e.g. `clerk`), a provider `event_id` that is unique (the idempotency key), an `event_type`, the raw `payload` (JSON), a `received_at` timestamp, a `processed` flag, and an optional `error`. A given `(provider, event_id)` SHALL appear at most once.

#### Scenario: Duplicate event id is rejected

- **WHEN** two webhook deliveries share the same provider `event_id`
- **THEN** only the first is stored/applied; the second is recognized as already processed

### Requirement: Organization suspension lifecycle

The `Organization` entity SHALL support a suspension lifecycle: in addition to `status` (`active` | `suspended`), it SHALL have a nullable `suspended_at` timestamp set when the organization is suspended and cleared when it is reactivated. Suspension is a soft state that retains all child data (companies, invoices, lines).

#### Scenario: Suspension sets the timestamp

- **WHEN** an organization is suspended
- **THEN** `status` is `suspended` and `suspended_at` is set, while its companies and invoices remain

#### Scenario: Reactivation clears the timestamp

- **WHEN** a suspended organization is reactivated
- **THEN** `status` is `active` and `suspended_at` is null

### Requirement: User access revocation

Revoking a user (membership removed or user deleted in Clerk) SHALL remove that user's ability to access the organization via the API, without corrupting records that reference the user. Nullable references to the user (e.g. `File.uploaded_by`) SHALL be cleared rather than left dangling.

#### Scenario: Revoked user cannot authenticate into the org

- **WHEN** a user's membership is revoked
- **THEN** subsequent requests by that user are not provisioned into the organization

#### Scenario: References remain valid after revocation

- **WHEN** a user who uploaded a file is revoked
- **THEN** the file record remains valid with its `uploaded_by` cleared (not pointing to a missing user)
