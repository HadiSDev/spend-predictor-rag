## ADDED Requirements

### Requirement: Expose the ERP connector catalog

The API SHALL expose `GET /api/v1/erp-types` returning the connector types registered in
the connector registry, so a client can present the available ERP systems and the
credential fields each one needs without hardcoding them.

- Each entry SHALL carry the `erp_type` key used by integration creation, a
  human-readable `label`, and a `credential_fields` list.
- Each credential field descriptor SHALL carry its `name`, a human-readable `label`,
  whether it is `required`, whether it is `secret`, and MAY carry a `default`.
- A field marked `secret` SHALL never have its stored value returned by any endpoint;
  the descriptor describes the input, not a value.
- The endpoint SHALL require authentication but SHALL NOT require management
  authorization — the catalog is not tenant data.
- The catalog SHALL be derived from the registry at runtime, so registering a new
  connector makes it appear with no further API change.

#### Scenario: Catalog lists the registered connectors

- **WHEN** an authenticated caller GETs `/api/v1/erp-types`
- **THEN** the response lists every registered connector — currently the `mock` debug
  connector — each with its label and credential field descriptors

#### Scenario: Catalog drives a valid integration creation

- **WHEN** a manager creates a company or an integration using an `erp_type` returned by
  the catalog
- **THEN** the request is accepted, and any `erp_type` absent from the catalog is
  rejected 4xx

#### Scenario: Unauthenticated access is refused

- **WHEN** an unauthenticated request GETs `/api/v1/erp-types`
- **THEN** the API responds `401 Unauthorized`

### Requirement: An integration may originate from company creation

An `ErpIntegration` SHALL be creatable either standalone via
`POST /api/v1/erp-integrations` or as part of company creation via
`POST /api/v1/companies`. Both paths SHALL apply the same rules: management
authorization, a registered `erp_type`, encryption of credentials at rest, and no
credential values in any response. `POST /api/v1/erp-integrations` SHALL remain available
for attaching an additional or replacement integration to a company that already exists.

#### Scenario: Integration created with a company behaves like any other

- **WHEN** an integration is created as part of `POST /api/v1/companies`
- **THEN** it is listed by `GET /api/v1/erp-integrations` for that company, and supports
  test-connection, refresh-accounts, disconnect, and reconnect identically to one created
  standalone

#### Scenario: A second integration is added later

- **WHEN** a manager POSTs `/api/v1/erp-integrations` for a company that already has one
- **THEN** the additional integration is created and both are listed for that company
