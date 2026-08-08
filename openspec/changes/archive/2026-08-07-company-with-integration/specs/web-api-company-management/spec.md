## MODIFIED Requirements

### Requirement: Create a company under the organization

The API SHALL provide `POST /api/v1/companies` to create a `Company` under the caller's
organization together with its ERP integration. The request SHALL require `name` and an
`integration` object, and MAY include `country_code` and `vat_number`. The `integration`
object SHALL require an `erp_type` that is a registered connector, and MAY include a
`label` and a `credentials` map. On success it SHALL return `201 Created` with the created
company and its integration.

The company, its `ErpIntegration`, and its encrypted `ErpCredential` SHALL be persisted in
a **single transaction**: if any part fails, none of them SHALL be persisted. Supplied
credentials SHALL be stored encrypted and SHALL NOT appear in the response.

The caller MUST be authorized to manage (system admin or org `admin`/`moderator`); a
system admin MAY target another organization via an explicit `organization_id`, while
other callers create only within their own organization.

This requirement binds at creation time only. Companies that already exist without an
integration SHALL remain valid and readable.

#### Scenario: Admin creates the first company with its integration

- **WHEN** an authorized caller POSTs `{ "name": "Acme A/S", "country_code": "DK", "integration": { "erp_type": "mock", "credentials": { "base_url": "http://localhost:8001", "api_key": "mock-secret" } } }`
- **THEN** a `Company` is created under the caller's organization, an `ErpIntegration` of
  type `mock` is created for it with its credentials stored encrypted, and both are
  returned with `201` — with no credential values in the response

#### Scenario: Missing integration is rejected

- **WHEN** an authorized caller POSTs `{ "name": "Acme A/S" }` with no `integration`
- **THEN** the API responds `422 Unprocessable Entity` and creates neither a company nor
  an integration

#### Scenario: Unknown erp_type creates nothing

- **WHEN** the request names an `erp_type` that is not a registered connector
- **THEN** the API responds `422 Unprocessable Entity` and no company, integration, or
  credential is persisted

#### Scenario: Integration failure rolls the company back

- **WHEN** the company row is written but persisting the integration or its credential
  fails
- **THEN** the whole transaction is rolled back and no company exists afterwards

#### Scenario: Unauthorized role cannot create

- **WHEN** a `viewer` or `member` POSTs to `/api/v1/companies`
- **THEN** the API responds `403 Forbidden` and no company is created

#### Scenario: Missing name is rejected

- **WHEN** the request body has no `name`
- **THEN** the API responds `422 Unprocessable Entity` and creates nothing
