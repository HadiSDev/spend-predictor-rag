## ADDED Requirements

### Requirement: Create a company under the organization

The API SHALL provide `POST /api/v1/companies` to create a `Company` under the caller's organization. The request SHALL require `name` and MAY include `country_code` and `vat_number`. On success it SHALL return `201 Created` with the created company. The caller MUST be authorized to manage (system admin or org `admin`/`moderator`); a system admin MAY target another organization via an explicit `organization_id`, while other callers create only within their own organization.

#### Scenario: Admin creates the first company

- **WHEN** an authorized caller POSTs `{ "name": "Acme A/S", "country_code": "DK" }`
- **THEN** a `Company` is created under the caller's organization and returned with `201`

#### Scenario: Unauthorized role cannot create

- **WHEN** a `viewer` or `member` POSTs to `/api/v1/companies`
- **THEN** the API responds `403 Forbidden` and no company is created

#### Scenario: Missing name is rejected

- **WHEN** the request body has no `name`
- **THEN** the API responds `422 Unprocessable Entity` and creates nothing

### Requirement: Update a company

The API SHALL provide `PATCH /api/v1/companies/{id}` to update a company's `name`, `country_code`, or `vat_number`. The company MUST belong to the caller's organization (or the caller is a system admin), otherwise the API SHALL respond `404 Not Found`. The caller MUST be authorized to manage.

#### Scenario: Authorized update

- **WHEN** an org `moderator` PATCHes a company in their org with `{ "vat_number": "DK12345678" }`
- **THEN** the field is updated and the updated company is returned with `200`

#### Scenario: Company in another organization is not found

- **WHEN** an authorized caller PATCHes a company id belonging to a different organization
- **THEN** the API responds `404 Not Found` and makes no change

### Requirement: Deactivate and reactivate a company

The API SHALL provide `POST /api/v1/companies/{id}/deactivate` and `POST /api/v1/companies/{id}/activate` to soft-deactivate and reactivate a company. Deactivation SHALL set `is_active = false` and record `deactivated_at`; reactivation SHALL set `is_active = true` and clear `deactivated_at`. Companies SHALL NOT be hard-deleted (they own financial data). The caller MUST be authorized to manage and the company MUST be in scope.

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
