## ADDED Requirements

### Requirement: Browser cross-origin access is configurable

The API SHALL support cross-origin requests from a configured set of origins so
a browser front-end can call it. Allowed origins SHALL come from configuration
(`WEB_API_CORS_ORIGINS`, comma-separated) and SHALL default to empty (no
cross-origin access) so enabling it is explicit.

#### Scenario: Configured origin is allowed

- **WHEN** a browser on an origin listed in `WEB_API_CORS_ORIGINS` calls the API
- **THEN** the response includes the CORS headers permitting that origin

#### Scenario: Default is closed

- **WHEN** no origins are configured
- **THEN** no cross-origin origin is granted access by default

### Requirement: Current-user endpoint

The API SHALL provide `GET /api/v1/users/me` returning the authenticated user's
`id`, `email`, `name`, organization `role`, `is_system_admin`, and
`organization_id`. It SHALL NOT expose external identifiers or secrets.

#### Scenario: Authenticated caller reads their profile

- **WHEN** an authenticated user requests `/users/me`
- **THEN** the response is their own profile including role and system-admin flag

#### Scenario: Unauthenticated request is rejected

- **WHEN** a request without a valid token calls `/users/me`
- **THEN** the API responds `401 Unauthorized`

### Requirement: Organization member directory

The API SHALL provide `GET /api/v1/users` listing the members of the caller's
organization (paginated), each with `id`, `email`, `name`, `role`, and
`is_system_admin`. The list SHALL be scoped to the caller's organization and
SHALL be read-only — roles are managed in Clerk, not through this endpoint.

#### Scenario: Members are org-scoped

- **WHEN** a user lists members
- **THEN** only users in the caller's organization are returned

#### Scenario: No cross-tenant leakage

- **WHEN** a user of one organization lists members
- **THEN** users of other organizations are never included

### Requirement: Tenant-scoped vendor list

The API SHALL provide `GET /api/v1/vendors` returning the vendors the caller's
organization transacts with — the distinct vendors referenced by invoices whose
company is in the caller's scope — with an optional `q` substring filter on name
or VAT number, and pagination. It SHALL NOT return vendors that only other
tenants reference.

#### Scenario: Only the org's vendors are listed

- **WHEN** a user lists vendors
- **THEN** the result contains exactly the vendors referenced by that
  organization's invoices

#### Scenario: Search filters by name or VAT

- **WHEN** a user passes `q`
- **THEN** only vendors whose name or VAT number contains `q` are returned

#### Scenario: Foreign company filter is rejected

- **WHEN** a user passes a `company_id` outside their scope
- **THEN** the API responds `404 Not Found`
