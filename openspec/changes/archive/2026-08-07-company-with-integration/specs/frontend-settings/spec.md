## MODIFIED Requirements

### Requirement: Company management

The Companies section SHALL list the organization's companies from
`GET /api/v1/companies`, including inactive ones behind an explicit toggle
(`include_inactive`), showing name, country, VAT number, and active state. An
authorized caller SHALL be able to create a company (`POST /api/v1/companies`),
edit its name, country code, and VAT number (`PATCH /api/v1/companies/{id}`), and
deactivate or reactivate it
(`POST /api/v1/companies/{id}/deactivate|activate`). Companies SHALL never be
presented as hard-deletable, matching the API's soft-deactivation model. After a
successful mutation the company list SHALL be refetched so the table reflects
server state.

Creating a company SHALL also connect its ERP system in the same dialog. The create form
SHALL include an ERP connection section offering the connector types from
`GET /api/v1/erp-types` and rendering an input per credential field that the chosen
connector declares, marking secret fields as password inputs and prefilling any declared
defaults. When exactly one connector type is available it SHALL be preselected. Submission
SHALL be blocked until the required connection fields are filled, and the company and its
integration SHALL be sent as one `POST /api/v1/companies` request.

Editing a company SHALL also expose its ERP connection, scoped to what the API supports on
an existing integration:

- The connector type SHALL be shown but SHALL NOT be changeable, since the API offers no
  way to change it.
- The integration's `label` SHALL be editable via `PATCH /api/v1/erp-integrations/{id}`.
- Credentials SHALL NOT be prefilled — the API never returns them. Replacing them SHALL be
  a deliberate act behind an explicit control, and SHALL make clear that **all** credential
  fields are replaced, since the API stores them as one map. Leaving that control untouched
  SHALL send no `credentials` and leave the stored secret unchanged.
- Whether credentials are currently stored SHALL be shown (from `has_credentials`), never
  their values.
- A company with **no** integration SHALL be offered the full connect form instead —
  connector picker and credential fields — submitting to `POST /api/v1/erp-integrations`,
  so a company created before this change can be connected.
- A company with **several** integrations SHALL edit its first connected one and SHALL say
  that the others exist rather than silently hiding them.

Company fields and integration fields SHALL be submitted as separate requests, since they
are separate resources; a failure of either SHALL be surfaced and SHALL NOT be reported as
success.

#### Scenario: Companies are listed

- **WHEN** the Companies section loads
- **THEN** the organization's active companies are listed with their details

#### Scenario: Inactive companies are revealed

- **WHEN** the user enables the "show inactive" toggle
- **THEN** the list is refetched with `include_inactive=true` and deactivated
  companies appear, visibly marked as inactive

#### Scenario: A company is created with its ERP connection

- **WHEN** an authorized user submits a new company with a name and the required ERP
  connection fields
- **THEN** a single `POST /api/v1/companies` carrying both the company fields and the
  `integration` block is called, a confirmation is shown, and the new company appears in
  the list

#### Scenario: The connector picker is data-driven

- **WHEN** the create dialog opens
- **THEN** the connector options and their credential inputs come from
  `GET /api/v1/erp-types`, and with only the debug connector registered it is the sole
  option and is preselected

#### Scenario: Missing connection details block submission

- **WHEN** an authorized user submits the create form with a name but a required
  credential field left empty
- **THEN** the field is marked invalid, no request is sent, and no company is created

#### Scenario: A company is edited

- **WHEN** an authorized user changes a company's details and saves without touching the
  ERP connection
- **THEN** only the changed company fields are sent as a partial update, no integration
  request is made, and the list reflects the result

#### Scenario: An integration's label is renamed

- **WHEN** an authorized user changes the integration's label in the edit dialog and saves
- **THEN** `PATCH /api/v1/erp-integrations/{id}` is called with the label alone and no
  `credentials` key, leaving the stored secret untouched

#### Scenario: Credentials are replaced deliberately

- **WHEN** an authorized user enables the replace-credentials control, fills every field,
  and saves
- **THEN** `PATCH /api/v1/erp-integrations/{id}` is called with the full credentials map,
  and the dialog states beforehand that all credentials are replaced

#### Scenario: Stored credentials are reported, never shown

- **WHEN** the edit dialog opens for an integration with `has_credentials: true`
- **THEN** it states that credentials are set, prefills no credential input, and displays
  no secret value

#### Scenario: A company with no integration can be connected

- **WHEN** an authorized user edits a company that has no integration
- **THEN** the full connect form is offered and submitting it calls
  `POST /api/v1/erp-integrations` for that company

#### Scenario: A failed integration update is not reported as success

- **WHEN** the company update succeeds but the integration request is rejected
- **THEN** the error is surfaced and the dialog does not claim the change succeeded

#### Scenario: A company is deactivated and restored

- **WHEN** an authorized user deactivates a company and confirms, then later
  reactivates it
- **THEN** the corresponding endpoint is called each time and the company's
  active state in the list follows, with no delete action offered at any point

#### Scenario: Empty state

- **WHEN** the organization has no companies
- **THEN** an explicit empty state invites the user to create the first one,
  rather than showing a bare table
