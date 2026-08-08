## Why

A company with no ERP integration is inert — nothing syncs, no entries arrive, no
invoices get categorized, and every report for it is empty. Today `POST /api/v1/companies`
happily creates such a company, and connecting the ERP is a separate, easily-forgotten
step through `POST /api/v1/erp-integrations`. Onboarding should not be able to produce a
dead company: creating the legal entity and connecting the system its data comes from are
one act, and they should succeed or fail together.

## What Changes

- **BREAKING** `POST /api/v1/companies` SHALL require an `integration` block
  (`erp_type`, optional `label`, `credentials`). Requests without it are rejected `422`
  and create nothing. The company, its `ErpIntegration`, and the encrypted
  `ErpCredential` are written in a **single transaction** — no orphan company can be
  left behind by a partial failure.
- The create response returns the created company **and** its integration (non-secret
  fields only; credentials are never echoed, consistent with the existing integration
  endpoints).
- New `GET /api/v1/erp-types` returns the registered connector catalog from
  `available_connectors()`, each entry carrying a display label and its credential field
  descriptors (name, required, secret). Today that is the single debug connector,
  `mock`; a future real connector appears with no front-end change.
- The Add-company dialog in Settings → Companies gains a required **ERP connection**
  section: connector picker sourced from `GET /erp-types`, plus the credential fields it
  declares. With only `mock` registered, the picker shows one option and is preselected.
- The Edit-company dialog gains the same section, scoped to what the API supports on an
  existing integration: its **label** and a deliberate **replacement** of its credentials.
  The connector type is shown but not changeable. Because credentials are write-only,
  nothing is prefilled — replacing them means entering every field. A company with no
  integration (created before this change) gets the full connect form instead.
- `POST /api/v1/erp-integrations` is unchanged and remains the path for attaching an
  additional or replacement integration to an existing company.
- Companies that already exist without an integration stay valid and readable. The
  requirement binds at creation time only; no migration or backfill is performed.

## Capabilities

### New Capabilities

None. The work extends two existing web-API capabilities and the settings front-end.

### Modified Capabilities

- `web-api-company-management`: company creation now requires and atomically provisions
  an ERP integration; the create response shape gains the integration.
- `web-api-erp-integration-management`: adds the `GET /api/v1/erp-types` connector
  catalog, and records that an integration may also originate from company creation.
- `frontend-settings`: the Companies section's create flow collects ERP connection
  details and blocks submission until they are valid.

## Impact

- **API (breaking)**: `POST /api/v1/companies` request and response schemas. Any existing
  caller sending `{name}` alone starts failing `422` — including
  `tests/web_api/test_management.py`, which must be updated.
- **Code**: `src/web_api/routers/companies.py` (transactional create), `src/web_api/schemas.py`
  (`CompanyCreate`, new `CompanyCreateResult`, ERP-type catalog models),
  `src/web_api/routers/erp_integrations.py` (`GET /erp-types`),
  `src/web_api/connectors/` (per-connector display label + credential field descriptors).
- **Front-end**: `frontend/src/components/settings/companies-panel.tsx`,
  `frontend/src/lib/companies.ts`, `frontend/src/lib/types.ts`, plus a new ERP-types query.
- **Data**: no schema migration. `ErpIntegration` and `ErpCredential` tables are used as
  they stand.
- **Out of scope**: backfilling integrations for existing companies, requiring a live
  connection test before the company is accepted, and any real (non-debug) connector.
