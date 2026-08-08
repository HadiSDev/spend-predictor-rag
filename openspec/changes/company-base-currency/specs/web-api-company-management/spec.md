## MODIFIED Requirements

### Requirement: Create a company under the organization

The API SHALL provide `POST /api/v1/companies` to create a `Company` under the caller's
organization together with its ERP integration. The request SHALL require `name`,
`base_currency`, and an `integration` object, and MAY include `country_code` and
`vat_number`. `base_currency` SHALL be a valid ISO 4217 alphabetic code, stored
uppercased; an invalid code SHALL be rejected. The `integration`
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

- **WHEN** an authorized caller POSTs `{ "name": "Acme A/S", "country_code": "DK", "base_currency": "DKK", "integration": { "erp_type": "mock", "credentials": { "base_url": "http://localhost:8001", "api_key": "mock-secret" } } }`
- **THEN** a `Company` is created under the caller's organization with base currency
  `DKK`, an `ErpIntegration` of type `mock` is created for it with its credentials
  stored encrypted, and both are returned with `201` — with no credential values in
  the response

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

### Requirement: Update a company

The API SHALL provide `PATCH /api/v1/companies/{id}` to update a company's `name`, `country_code`, `vat_number`, or `base_currency`. A supplied `base_currency` SHALL be validated as an ISO 4217 alphabetic code and stored uppercased. Changing `base_currency` SHALL NOT rewrite the company's already-stored converted amounts as part of the request; those are rewritten by an explicit recompute. The company MUST belong to the caller's organization (or the caller is a system admin), otherwise the API SHALL respond `404 Not Found`. The caller MUST be authorized to manage.

#### Scenario: Authorized update

- **WHEN** an org `moderator` PATCHes a company in their org with `{ "vat_number": "DK12345678" }`
- **THEN** the field is updated and the updated company is returned with `200`

#### Scenario: Base currency is changed

- **WHEN** an authorized caller PATCHes `{ "base_currency": "eur" }`
- **THEN** the company reports `EUR` and the response returns `200` without rewriting
  historical rows

#### Scenario: Invalid base currency is rejected

- **WHEN** an authorized caller PATCHes `{ "base_currency": "E" }`
- **THEN** the API responds `422 Unprocessable Entity` and the company is unchanged

#### Scenario: Company in another organization is not found

- **WHEN** an authorized caller PATCHes a company id belonging to a different organization
- **THEN** the API responds `404 Not Found` and makes no change

## ADDED Requirements

### Requirement: Company reads expose the base currency

`GET /api/v1/companies` and every company payload the API returns SHALL include
`base_currency`, so a client can label and format that company's figures without
a second lookup.

#### Scenario: Base currency is returned with the company

- **WHEN** a client lists or creates companies
- **THEN** each returned company carries its `base_currency`

### Requirement: Stored conversions can be recomputed for a company

The API SHALL provide `POST /api/v1/companies/{id}/recompute-fx`, which
recomputes that company's stored base-currency amounts against its current
`base_currency`, using each row's own historical rate. The caller MUST be
authorized to manage, and the company MUST be in the caller's scope, otherwise
the API SHALL respond `404 Not Found`.

The response SHALL report how many rows were converted, left unconverted, and
left unchanged. Original posted currencies and amounts SHALL NOT be modified.

#### Scenario: Recompute after a base-currency change

- **WHEN** an authorized caller changes a company's base currency and then POSTs
  to `/companies/{id}/recompute-fx`
- **THEN** the company's rows are rewritten in the new base currency at each
  row's historical rate, and counts of converted/unconverted/unchanged rows are
  returned

#### Scenario: Unauthorized role cannot recompute

- **WHEN** a `viewer` or `member` POSTs to `/companies/{id}/recompute-fx`
- **THEN** the API responds `403 Forbidden` and no row is rewritten

#### Scenario: Foreign company is not found

- **WHEN** a caller targets a company outside their organization
- **THEN** the API responds `404 Not Found` and rewrites nothing
