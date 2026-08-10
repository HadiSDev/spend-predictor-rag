## ADDED Requirements

### Requirement: A company's spend tree can be assigned and changed

The API SHALL let an authorized caller assign a company's spend tree via `PATCH /api/v1/companies/{id}` with `spend_tree_id`. The tree MUST belong to the company's organization, otherwise the API SHALL respond `404 Not Found`. `CompanyRead` SHALL carry `spend_tree_id` and the tree's name, so a client can show which taxonomy a company categorizes against without a second request.

Changing the assignment SHALL apply the reassignment rule in one transaction with the update: pointers into the old tree are cleared, stored levels and statuses are untouched, and the affected lines become stale. The response SHALL report how many lines were affected, so the caller learns the consequence at the moment they cause it.

#### Scenario: Assigning a tree

- **WHEN** a manager PATCHes a company with a `spend_tree_id` belonging to its organization
- **THEN** the company is assigned that tree and the response carries the tree's id and name

#### Scenario: A tree from another organization is rejected

- **WHEN** the PATCH names a tree in a different organization
- **THEN** the API responds `404 Not Found` and the assignment is unchanged

#### Scenario: The caller is told what the change cost

- **WHEN** a reassignment leaves 42 lines with an unresolvable category
- **THEN** the response reports 42 affected lines and those lines are flagged stale

#### Scenario: Unauthorized role cannot reassign

- **WHEN** a `member` or `viewer` PATCHes `spend_tree_id`
- **THEN** the API responds `403 Forbidden` and the assignment is unchanged

## MODIFIED Requirements

### Requirement: Create a company under the organization

The API SHALL provide `POST /api/v1/companies` to create a `Company` under the caller's
organization together with its ERP integration. The request SHALL require `name`,
`base_currency`, and an `integration` object, and MAY include `country_code`,
`vat_number`, and `spend_tree_id`. `base_currency` SHALL be a valid ISO 4217 alphabetic code, stored
uppercased; an invalid code SHALL be rejected. The `integration`
object SHALL require an `erp_type` that is a registered connector, and MAY include a
`label` and a `credentials` map. On success it SHALL return `201 Created` with the created
company and its integration.

When `spend_tree_id` is supplied it MUST name a tree in the same organization, otherwise the request SHALL be rejected. When it is omitted, the company SHALL be assigned the organization's default-template spend tree, creating that copy from the platform template if the organization does not have one yet — so a company is never left without a taxonomy to categorize against, exactly as it is never left without an ERP connection.

The company, its `ErpIntegration`, its encrypted `ErpCredential`, and any default-tree copy created for it SHALL be persisted in
a **single transaction**: if any part fails, none of them SHALL be persisted. Supplied
credentials SHALL be stored encrypted and SHALL NOT appear in the response.

The caller MUST be authorized to manage (system admin or org `admin`/`moderator`); a
system admin MAY target another organization via an explicit `organization_id`, while
other callers create only within their own organization.

This requirement binds at creation time only. Companies that already exist without an
integration SHALL remain valid and readable.

#### Scenario: Admin creates the first company with its integration

- **WHEN** an authorized caller POSTs `{ "name": "Acme A/S", "country_code": "DK", "base_currency": "DKK", "integration": { "erp_type": "mock", "credentials": { "base_url": "http://localhost:8001", "api_key": "mock-secret" } } }`
- **THEN** a `Company` is created under the caller's organization with base currency
  `DKK`, an `ErpIntegration` of type `mock` is created for it with its credentials
  stored encrypted, and both are returned with `201` — with no credential values in
  the response

#### Scenario: The first company materializes the organization's default tree

- **WHEN** the first company of an organization is created with no `spend_tree_id`
- **THEN** a default-template tree is created for that organization and the company is assigned it, in the same transaction as the company

#### Scenario: A second company reuses the same default copy

- **WHEN** a second company is created in that organization with no `spend_tree_id`
- **THEN** it is assigned the existing default-template tree and no second copy is created

#### Scenario: A tree from another organization creates nothing

- **WHEN** the request names a `spend_tree_id` belonging to another organization
- **THEN** the API responds `422 Unprocessable Entity` and no company, integration, or credential is persisted

#### Scenario: Missing base currency is rejected

- **WHEN** an authorized caller POSTs a company with no `base_currency`
- **THEN** the API responds `422 Unprocessable Entity` and creates neither a company nor
  an integration

#### Scenario: Invalid base currency creates nothing

- **WHEN** the request supplies `base_currency: "kroner"`
- **THEN** the API responds `422 Unprocessable Entity` and no company, integration, or
  credential is persisted

#### Scenario: Missing integration is rejected

- **WHEN** an authorized caller POSTs `{ "name": "Acme A/S", "base_currency": "DKK" }` with no `integration`
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
