# web-api-auth Specification

## Purpose
TBD - created by archiving change web-api-clerk-review. Update Purpose after archive.
## Requirements
### Requirement: Clerk session token verification

The web API SHALL authenticate every protected request by verifying a Clerk-issued session JWT presented in the `Authorization: Bearer <token>` header. Verification SHALL check the RS256 signature against Clerk's JWKS, and validate the `iss` (issuer), `aud` (audience when configured), and `exp`/`nbf` claims. The signing keys SHALL be fetched from the configured JWKS URL and cached, with a refresh on unknown `kid`.

#### Scenario: Valid token is accepted

- **WHEN** a request arrives with a `Bearer` token whose signature, issuer, audience, and expiry are valid
- **THEN** the request proceeds and the resolved principal (Clerk user id, org id, role) is available to the handler

#### Scenario: Missing or malformed Authorization header

- **WHEN** a request to a protected endpoint has no `Authorization` header or a header that is not a `Bearer` token
- **THEN** the API responds `401 Unauthorized` and no handler logic runs

#### Scenario: Invalid or expired token is rejected

- **WHEN** a request presents a token with a bad signature, wrong issuer/audience, or an expired `exp`
- **THEN** the API responds `401 Unauthorized` with a generic error and does not leak which check failed

#### Scenario: Verifier is injectable for tests

- **WHEN** the application is constructed with a fake verifier dependency
- **THEN** tests can authenticate requests without contacting Clerk or its JWKS endpoint

### Requirement: Just-in-time provisioning of Organization and User

On the first authenticated request from a Clerk principal, the API SHALL provision local records: it SHALL find-or-create an `Organization` linked by `clerk_org_id` and a `User` linked by `clerk_user_id` (belonging to that organization), and map the Clerk organization role to `User.role` (`admin`, `member`, or `viewer`). Provisioning SHALL be idempotent — repeated requests reuse the existing rows and update mutable attributes (name, email, role).

#### Scenario: First request creates local records

- **WHEN** an authenticated principal with a `clerk_org_id`/`clerk_user_id` not seen before makes a request
- **THEN** a matching `Organization` and `User` are created and linked by their Clerk IDs, with the mapped role

#### Scenario: Subsequent requests reuse records

- **WHEN** the same principal makes further requests
- **THEN** no duplicate `Organization` or `User` rows are created, and changed name/email/role values are updated in place

#### Scenario: Unknown Clerk role maps to least privilege

- **WHEN** the Clerk organization role does not map to a known application role
- **THEN** the user is provisioned as `viewer`

### Requirement: Tenant-scoped request context

The API SHALL expose a shared dependency that resolves the authenticated request to its `organization_id` and the set of `company_id`s the caller may access. All data endpoints SHALL obtain their scope exclusively from this dependency and SHALL NOT accept a tenant identifier from the client that widens access.

#### Scenario: Data access is confined to the caller's organization

- **WHEN** an authenticated caller requests data
- **THEN** only rows whose `company` belongs to the caller's `organization_id` are eligible to be returned

#### Scenario: Cross-tenant identifier is not honored

- **WHEN** a caller supplies a `company_id` that belongs to another organization
- **THEN** the API responds `404 Not Found` (or an empty result) and never returns the other tenant's rows

