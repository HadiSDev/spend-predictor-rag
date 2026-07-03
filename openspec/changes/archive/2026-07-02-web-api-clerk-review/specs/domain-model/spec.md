## ADDED Requirements

### Requirement: External identity linkage for Organization and User

The domain model SHALL allow `Organization` and `User` records to be linked to an external identity provider (Clerk). `Organization` SHALL have a nullable, unique `clerk_org_id`, and `User` SHALL have a nullable, unique `clerk_user_id`. These fields carry the provider's principal identifiers so authenticated requests can be mapped to local records. They are NULL for records not backed by an external provider (e.g. synthetic/demo tenants), and MUST be unique when present so a Clerk principal maps to exactly one local record.

#### Scenario: Clerk organization maps to one Organization

- **WHEN** an authenticated request carries a `clerk_org_id`
- **THEN** it resolves to at most one `Organization` (the row whose `clerk_org_id` matches), or triggers creation of one if none exists

#### Scenario: Clerk user maps to one User

- **WHEN** an authenticated request carries a `clerk_user_id`
- **THEN** it resolves to at most one `User`, scoped to the organization identified by the request's `clerk_org_id`

#### Scenario: Synthetic tenants have no external identity

- **WHEN** a demo/synthetic `Organization` or `User` is created by the sync runner
- **THEN** its `clerk_org_id` / `clerk_user_id` is NULL and the record remains valid
