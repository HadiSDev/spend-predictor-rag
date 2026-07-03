## ADDED Requirements

### Requirement: Read the caller's organization profile

The API SHALL provide `GET /api/v1/organization` returning the authenticated caller's organization profile, including at least `id`, `name`, `slug`, `status`, and `created_at`. Any authenticated member of the organization (including `viewer`) MAY read it.

#### Scenario: Member reads their organization

- **WHEN** an authenticated caller requests `GET /api/v1/organization`
- **THEN** the response is the caller's own organization profile

#### Scenario: Only the caller's organization is returned

- **WHEN** the caller belongs to organization A
- **THEN** the response describes organization A and never another organization

### Requirement: Update the organization profile

The API SHALL provide `PATCH /api/v1/organization` to update the organization's `name` and `slug`. The caller MUST be a system admin or org `admin` (org profile is more sensitive than company management — `moderator` MAY NOT update it). `slug` MUST remain unique; a conflicting slug SHALL yield `409 Conflict`.

#### Scenario: Admin updates the profile

- **WHEN** an org `admin` PATCHes `{ "name": "Acme Group" }`
- **THEN** the organization name is updated and the profile returned with `200`

#### Scenario: Moderator cannot update the organization

- **WHEN** an org `moderator` PATCHes `/api/v1/organization`
- **THEN** the API responds `403 Forbidden` and makes no change

#### Scenario: Duplicate slug is rejected

- **WHEN** an admin sets a `slug` already used by another organization
- **THEN** the API responds `409 Conflict` and makes no change
