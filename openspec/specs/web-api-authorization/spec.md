# web-api-authorization Specification

## Purpose
TBD - created by archiving change org-company-management. Update Purpose after archive.
## Requirements
### Requirement: Platform and organization role model

The API SHALL recognize two authorization dimensions. A **platform** dimension: a user is either a system admin (`User.is_system_admin = true`) or not. An **organization** dimension: each user has exactly one org role in `admin`, `moderator`, `member`, or `viewer`. Write access to management operations SHALL require the caller to be a system admin OR to hold an org role of `admin` or `moderator`. `member` and `viewer` SHALL have no write access. `viewer` is read-only.

#### Scenario: Admin and moderator may write

- **WHEN** a user whose org role is `admin` or `moderator` calls a management endpoint
- **THEN** the authorization layer permits the operation (subject to tenant scope)

#### Scenario: Member and viewer are read-only

- **WHEN** a user whose org role is `member` or `viewer` calls a management (write) endpoint
- **THEN** the API responds `403 Forbidden` and makes no change

#### Scenario: System admin may manage any organization

- **WHEN** a system admin calls a management endpoint
- **THEN** the operation is permitted regardless of their org role, and is not confined to a single organization

### Requirement: Provisioning roles and system-admin from Clerk claims

Just-in-time provisioning SHALL map the Clerk organization role to the app org role, now including `moderator` (a Clerk role resolving to `moderator` yields org role `moderator`); unknown roles still default to `viewer`. It SHALL set `User.is_system_admin` from a configurable Clerk claim (`CLERK_SYSTEM_ADMIN_CLAIM`); when the claim is absent or false, the user is not a system admin. These attributes SHALL be refreshed on each request like other mutable user fields.

#### Scenario: Moderator role is provisioned

- **WHEN** a caller's verified token carries an org role that maps to `moderator`
- **THEN** the provisioned `User.role` is `moderator`

#### Scenario: System-admin claim provisions the flag

- **WHEN** a caller's verified token carries a truthy value for the configured system-admin claim
- **THEN** the provisioned `User.is_system_admin` is `true`

#### Scenario: Absent system-admin claim yields a normal user

- **WHEN** a caller's token has no system-admin claim
- **THEN** `User.is_system_admin` is `false`

### Requirement: Shared write-authorization dependency

The API SHALL expose a reusable request dependency that resolves the caller and raises `403 Forbidden` unless they are authorized to manage (system admin OR org `admin`/`moderator`). Management endpoints SHALL depend on it rather than re-implementing role checks. For non–system-admin callers the dependency SHALL preserve tenant scoping so writes only affect the caller's own organization.

#### Scenario: Unauthorized role is blocked before any side effect

- **WHEN** a `viewer` calls `POST /api/v1/companies`
- **THEN** the API responds `403 Forbidden` and no company is created

#### Scenario: Authorized non–system-admin is confined to their organization

- **WHEN** an org `admin` performs a management operation
- **THEN** the operation may target only entities within that admin's own organization

