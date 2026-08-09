## MODIFIED Requirements

### Requirement: Expose the ERP connector catalog

The API SHALL expose `GET /api/v1/erp-types` returning the connector types registered in
the connector registry, so a client can present the available ERP systems and the
credential fields each one needs without hardcoding them.

- Each entry SHALL carry the `erp_type` key used by integration creation, a
  human-readable `label`, and a `credential_fields` list.
- Each entry MAY additionally carry brand metadata declared by the connector: a
  `brand_slug` naming its artwork, a `description` of the ERP in one line, and a
  `docs_url`. Each is optional and SHALL be absent for a connector that declares
  none, so the addition breaks no existing client.
- A client SHALL be able to render a recognisable, branded chooser from this
  payload alone, without knowing any connector by name — the catalog is the only
  place a connector's identity is declared.
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
- **THEN** the response lists every registered connector — the `mock` debug
  connector and `billy` — each with its label and credential field descriptors

#### Scenario: Catalog carries brand metadata when a connector declares it

- **WHEN** an authenticated caller GETs `/api/v1/erp-types`
- **THEN** the `billy` entry carries a `brand_slug`, a `description` and a
  `docs_url`, and an entry for a connector declaring none omits them

#### Scenario: Catalog drives a valid integration creation

- **WHEN** a manager creates a company or an integration using an `erp_type` returned by
  the catalog
- **THEN** the request is accepted, and any `erp_type` absent from the catalog is
  rejected 4xx

#### Scenario: Unauthenticated access is refused

- **WHEN** an unauthenticated request GETs `/api/v1/erp-types`
- **THEN** the API responds `401 Unauthorized`
