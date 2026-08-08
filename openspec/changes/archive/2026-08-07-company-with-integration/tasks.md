## 1. Connector catalog metadata

- [x] 1.1 Add a `CredentialField` Pydantic model (`name`, `label`, `required`, `secret`, `default`) to `src/web_api/connectors/base.py`
- [x] 1.2 Add `display_label: str` and `credential_fields: list[CredentialField]` class attributes to `ErpConnector`, defaulting to the class name and an empty list
- [x] 1.3 Declare `display_label = "Debug ERP"` and the `base_url` / `api_key` descriptors on `MockErpConnector` — both `required=False`, with the defaults it already applies, `api_key` marked `secret`
- [x] 1.4 Add `connector_catalog()` to `src/web_api/connectors/__init__.py` returning `(erp_type, class)` pairs for every registered connector

## 2. ERP-type catalog endpoint

- [x] 2.1 Add `ErpTypeRead` and `CredentialFieldRead` response schemas to `src/web_api/schemas.py`
- [x] 2.2 Add `GET /api/v1/erp-types` to `src/web_api/routers/erp_integrations.py`, authenticated but not management-gated, projecting the registry
- [x] 2.3 Test: authenticated caller gets the `mock` entry with its label and both credential descriptors; unauthenticated gets 401; a `viewer` still gets 200

## 3. Shared integration provisioning

- [x] 3.1 Create `src/web_api/integrations.py` with `provision_integration(session, company_id, spec) -> ErpIntegration` that validates `erp_type` against the registry (422 on unknown) and `session.add`s the integration without committing
- [x] 3.2 Validate the supplied `credentials` map in the helper: required descriptors present and non-empty, no undeclared keys — 422 otherwise
- [x] 3.3 Write an `ErpCredential` (encrypted) only when the credentials map is non-empty, so the minimal path never calls `encrypt_config`
- [x] 3.4 Refactor `create_integration` in `routers/erp_integrations.py` to use the helper, keeping its existing response and commit behaviour
- [x] 3.5 Test: existing `test_erp_integrations.py` suite still passes unchanged; add cases for a missing required field and an undeclared credential key

## 4. Atomic company + integration creation

- [x] 4.1 Add a required `integration: IntegrationSpec` field to `CompanyCreate` in `src/web_api/schemas.py` (`erp_type` required, `label` and `credentials` optional)
- [x] 4.2 Add `CompanyCreateResult(CompanyRead)` with an `integration: ErpIntegrationRead` field
- [x] 4.3 Rewrite `create_company` in `src/web_api/routers/companies.py` to build the `Company`, call `provision_integration`, and commit **once**; return the combined result
- [x] 4.4 Test: valid create returns 201 with company fields plus the integration, no credential values in the response, and both rows present in the DB
- [x] 4.5 Test: request without `integration` → 422 and no company row; unknown `erp_type` → 422 and no company row
- [x] 4.6 Test: a failure while persisting the integration leaves no company (rollback)
- [x] 4.7 Test: creating with real credentials (enc-key fixture) stores them encrypted and `has_credentials` is true
- [x] 4.8 Update the `_create` helper and affected cases in `tests/web_api/test_management.py` to send `{"erp_type": "mock"}`; confirm the authorization-matrix tests still assert 201/403 as before
- [x] 4.9 Run `uv run pytest` and fix any other suite that creates a company through the API

## 5. Front-end: ERP types + create flow

- [x] 5.1 Add `ErpTypeRead`, `CredentialFieldRead`, `IntegrationSpec`, and the updated `CompanyCreate` to `frontend/src/lib/types.ts`
- [x] 5.2 Add `erpTypesQueryOptions` (a new `frontend/src/lib/erp-types.ts` or an addition to an existing lib module) fetching `GET /api/v1/erp-types`
- [x] 5.3 Render an ERP connection section in `CompanyDialog` (`frontend/src/components/settings/companies-panel.tsx`) only when creating: connector `Select` from the query, one `Input` per declared credential field, `type="password"` for secrets, seeded with declared defaults
- [x] 5.4 Preselect the connector when exactly one type is available; require the connector and every `required` credential field before submit
- [x] 5.5 Compose the `integration` block into the single `POST /api/v1/companies` body in `createCompanyMutation` / the panel's `onCreate` contract
- [x] 5.6 Keep the edit dialog unchanged — no ERP section, still a partial update of changed company fields only

## 6. Front-end tests

- [x] 6.1 Test: the create dialog renders the connector option and credential inputs from a stubbed `GET /erp-types`, with the sole connector preselected
- [x] 6.2 Test: submitting a valid form issues one `POST /api/v1/companies` carrying both the company fields and the `integration` block
- [x] 6.3 Test: a required credential field left empty blocks submission and sends no request
- [x] 6.4 Test: opening the dialog on an existing company shows no ERP section and still sends only changed fields
- [x] 6.5 Run the front-end test suite via `./node_modules/.bin/vitest run` (do not invoke a package-manager script)

## 7. Edit the integration from the edit dialog

- [x] 7.1 Add `updateIntegrationMutation` and `connectIntegrationMutation` to a front-end lib module, and an `integrationsQueryOptions` fetching `GET /erp-integrations` for all in-scope companies
- [x] 7.2 Pass the integration rows into `CompaniesPanel` as a prop and hand each dialog its company's own, keeping the panel presentational
- [x] 7.3 Render the ERP section when editing: connector type as static text, an editable `label`, and a `has_credentials` note — no credential values prefilled
- [x] 7.4 Put credential replacement behind an explicit control that states all credentials are replaced; when off send no `credentials`, when on validate every required field
- [x] 7.5 Offer the full connect form when the company has no integration, submitting to `POST /erp-integrations`
- [x] 7.6 Say how many other integrations exist when a company has more than one, and edit the first connected one
- [x] 7.7 Submit company and integration as separate requests, surfacing either failure without claiming success
- [x] 7.8 Test: renaming the label sends the label alone with no `credentials` key
- [x] 7.9 Test: replacing credentials sends the full map; leaving the control off sends no integration request at all
- [x] 7.10 Test: `has_credentials` is reported with no secret rendered and no credential input prefilled
- [x] 7.11 Test: a company with no integration gets the connect form and submits `POST /erp-integrations`
- [x] 7.12 Test: a rejected integration request surfaces the error rather than reporting success
- [x] 7.13 Run the front-end suite and `tsc --noEmit`

## 8. Wrap-up

- [x] 8.1 Update `CLAUDE.md` — the endpoint list gains `GET /erp-types`, and the company-create line notes the required integration
- [x] 8.2 Note the edit-dialog integration behaviour in `CLAUDE.md`
- [x] 8.3 Run `uv run pytest` and the front-end suite together and confirm both are green before marking the change done
