## ADDED Requirements

### Requirement: Organization profile and lifecycle

The `Organization` entity SHALL be a first-class domain record beyond its Clerk mirror. It SHALL have a `slug` (nullable, unique when present — a human-readable handle, typically the Clerk org slug) and a `status` (`active` or `suspended`, default `active`). These are managed via the organization profile endpoints and provisioned from Clerk where available.

#### Scenario: New organization defaults to active

- **WHEN** an `Organization` is provisioned
- **THEN** its `status` is `active` and its `slug` may be null until set

#### Scenario: Slug is unique when present

- **WHEN** two organizations would have the same non-null `slug`
- **THEN** the second write is rejected (uniqueness violation)

### Requirement: Company activation state

The `Company` entity SHALL carry activation state: `is_active` (boolean, default `true`) and `deactivated_at` (timestamp, nullable). Deactivation is a soft state change that preserves the company and its financial data (invoices, invoice lines); companies are never hard-deleted through the API.

#### Scenario: Company defaults to active

- **WHEN** a `Company` is created
- **THEN** `is_active` is `true` and `deactivated_at` is null

#### Scenario: Deactivation preserves related data

- **WHEN** a company is deactivated
- **THEN** its `Invoice` and `InvoiceLine` rows are unchanged and still reference the company

### Requirement: Platform and organization roles

`User` SHALL carry a platform-level `is_system_admin` boolean (default `false`) in addition to its organization `role`. The organization `role` set SHALL be `admin`, `moderator`, `member`, or `viewer`. `is_system_admin` grants cross-organization management privileges independent of the org role.

#### Scenario: Default user is not a system admin

- **WHEN** a `User` is provisioned without a system-admin claim
- **THEN** `is_system_admin` is `false`

#### Scenario: Moderator is a valid organization role

- **WHEN** a user is assigned the `moderator` role
- **THEN** the value is accepted and treated as a write-capable organization role
