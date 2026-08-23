# web-api-company-management Specification

## Purpose
TBD - created by archiving change org-company-management. Update Purpose after archive.
## Requirements
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

### Requirement: Deactivate and reactivate a company

The API SHALL provide `POST /api/v1/companies/{id}/deactivate` and `POST /api/v1/companies/{id}/activate` to soft-deactivate and reactivate a company. Deactivation SHALL set `is_active = false` and record `deactivated_at`; reactivation SHALL set `is_active = true` and clear `deactivated_at`. Deactivation SHALL NOT destroy anything — a company owns financial data, and retiring it keeps every record. It is the only removal available to an organization's own admin; destroying a company outright is reserved to a platform system admin and specified in `company-deletion`. The caller MUST be authorized to manage and the company MUST be in scope.

#### Scenario: Deactivate is a soft state change

- **WHEN** an authorized caller deactivates a company
- **THEN** the company still exists with `is_active = false` and a `deactivated_at` timestamp, and its invoices/lines remain intact

#### Scenario: Reactivate restores active state

- **WHEN** an authorized caller activates a previously deactivated company
- **THEN** `is_active` is `true` and `deactivated_at` is null

### Requirement: Company listing reflects active state

The companies list (`GET /api/v1/companies`) SHALL exclude deactivated companies by default and SHALL include them when `include_inactive=true` is passed. Each returned company SHALL expose its `is_active` state.

#### Scenario: Deactivated companies are hidden by default

- **WHEN** a caller lists companies and one is deactivated
- **THEN** the deactivated company is omitted unless `include_inactive=true` is supplied

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

### Requirement: Delete a company

The API SHALL provide `DELETE /api/v1/companies/{id}`, restricted to a platform
system admin, which destroys the company and every record scoped to it in one
transaction.

- The caller MUST hold `is_system_admin`. An org `admin` or `moderator` — who may
  deactivate — SHALL receive `403`.
- When the company holds any invoice, line, posting or integration, the request
  SHALL be refused with `409` unless it carries `confirm=true`. The refusal body
  SHALL carry the counts and the earliest and latest accounting date.
- A company holding nothing SHALL delete without confirmation: there is nothing
  to preview and a gate would be ceremony.
- A refused request SHALL change nothing.
- The response SHALL report what was destroyed, so the caller's record of the
  action does not depend on having read the refusal first.

#### Scenario: A system admin deletes a company with records

- **WHEN** a system admin sends the request with `confirm=true` for a company
  holding invoices and postings
- **THEN** the company and its records are destroyed and the response reports the
  counts

#### Scenario: Without confirmation the request is refused

- **WHEN** the same request is sent without `confirm`
- **THEN** the response is `409` carrying the invoice, line, posting and
  integration counts and the accounting date span, and nothing is removed

#### Scenario: An org admin is refused

- **WHEN** an org admin sends the request for a company in their organization
- **THEN** the response is `403` and nothing is removed

#### Scenario: An empty company needs no confirmation

- **WHEN** a system admin deletes a company with no invoices and no postings and
  no `confirm`
- **THEN** the company is deleted

#### Scenario: A company in another organization

- **WHEN** a system admin deletes a company in an organization other than their
  own
- **THEN** it is deleted, since a system admin acts across organizations

#### Scenario: Deleting an unknown company

- **WHEN** the id names no company
- **THEN** the response is `404`
