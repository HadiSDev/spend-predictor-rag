## Context

`POST /api/v1/companies` ([companies.py:37](../../../src/web_api/routers/companies.py#L37)) creates
a bare `Company`. Connecting the ERP is a separate call to `POST /api/v1/erp-integrations`
([erp_integrations.py:89](../../../src/web_api/routers/erp_integrations.py#L89)), which
validates `erp_type` against the connector registry, persists the `ErpIntegration`, and
stores credentials as an encrypted `ErpCredential` (Fernet, `web_api/credentials.py`).
Nothing forces the second call, so onboarding can leave a company that syncs nothing.

Constraints that shape the design:

- `web_api` must not import `ai_api`. All of this stays in the domain package.
- The connector registry (`web_api/connectors/__init__.py`) is a name → class dict with
  `available_connectors()` returning the sorted names. Only `MockErpConnector` (`mock`)
  is registered — the debug ERP that talks to `mock_erp/`.
- Model ids are Python-side `uuid4` defaults (`db/models/_base.py`), so a child row's FK
  can be set before any flush.
- Credential encryption fails closed when `WEB_API_CREDENTIAL_ENC_KEY` is unset
  (`CredentialConfigError` → 500). Company creation must not inherit that failure mode
  for the common case.
- The front end is TanStack Start + react-hook-form; the create and edit dialogs are the
  same `CompanyDialog` component today.

## Goals / Non-Goals

**Goals:**

- Company creation and ERP connection are one atomic operation — no orphan company.
- The set of connectable ERP systems and the fields each needs is discoverable from the
  API, not hardcoded in the front end.
- Adding a real connector later requires registering a class, with no change to the
  companies router, the catalog endpoint, or the settings UI.

**Non-Goals:**

- Backfilling integrations onto companies that already exist.
- Proving the connection works before accepting the company (no forced
  `test-connection`); the user can run it afterwards from the integration.
- Fetching accounts (`refresh-accounts`) as part of creation.
- Any non-debug connector, and any change to sync behaviour.

## Decisions

### Catalog metadata lives on the connector class

`ErpConnector` gains two class attributes: `display_label: str` and
`credential_fields: list[CredentialField]`, where `CredentialField` is a Pydantic model
(`name`, `label`, `required`, `secret`, `default`). `GET /api/v1/erp-types` walks the
registry and projects these.

*Why:* the knowledge of "what this connector needs to authenticate" belongs next to the
code that consumes it. A registry-side lookup table would drift the moment someone adds a
connector and forgets the table.

*Alternative rejected:* deriving fields by introspecting `__init__` — fragile, and it
cannot express `label`/`secret`.

`MockErpConnector` declares `base_url` and `api_key`, both **not required**, with the
defaults it already applies (`http://localhost:8001`, `mock-secret`), and `api_key` marked
`secret`.

### Required-ness is validated against the descriptors, unknown keys are rejected

The create path checks the supplied `credentials` map against the chosen connector's
descriptors: every `required` field must be present and non-empty (else 422), and any key
not declared is rejected 422.

*Why reject unknowns:* a typo like `apikey` would otherwise be silently stored and surface
much later as an opaque auth failure during sync. Failing at the boundary is cheaper.

*Trade-off:* a connector taking free-form config must declare its fields. Acceptable —
there is one connector, and declaring fields is the point of the catalog.

### No `ErpCredential` row when `credentials` is empty

Because the debug connector's fields are optional with defaults, `{"erp_type": "mock"}`
alone is a valid integration. In that case no `ErpCredential` is written and
`encrypt_config` is never called — so company creation does not require
`WEB_API_CREDENTIAL_ENC_KEY` unless the caller actually supplies secrets.

*Why:* keeps the minimal onboarding path working in local/dev and in tests without
configuring encryption, while keeping the fail-closed guarantee for real secrets.

### One shared provisioning helper, one transaction

A new `web_api/integrations.py` exposes
`provision_integration(session, company_id, spec) -> ErpIntegration` that validates
`erp_type` and credentials, and **adds** (never commits) the `ErpIntegration` and its
optional `ErpCredential`. Both `POST /companies` and `POST /erp-integrations` call it;
each router owns its own commit.

`create_company` therefore becomes: build `Company` → `session.add` → call
`provision_integration` → single `session.commit()`. Since ids are client-side uuids, no
intermediate flush is needed and a failure anywhere rolls back everything. On
`HTTPException` from validation, nothing was committed, so the request ends with no rows.

*Why a helper over having the companies router import the erp_integrations router
function:* the router function owns commit/response concerns; the helper is the reusable
unit and keeps the two endpoints from drifting apart.

### Create response extends `CompanyRead` rather than nesting it

`POST /companies` returns `CompanyCreateResult(CompanyRead)` — every existing company
field at the top level, plus `integration: ErpIntegrationRead`.

*Why:* a client reading `response.id` keeps working; only the *request* is breaking. The
alternative (`{ "company": …, "integration": … }`) would break reads for no gain.

### Catalog endpoint requires authentication but not management

`GET /api/v1/erp-types` uses the plain authenticated dependency. It exposes no tenant
data and no secret values — only which connectors this deployment supports — and the
front end needs it wherever an integration is picked, including read-only contexts.

### Front end: one dialog, two modes of the same ERP section

`CompanyDialog` keeps one component and renders the ERP connection section in both modes.
The section renders a connector `Select` fed by an `erpTypesQueryOptions` query, and one
`Input` per declared credential field (`type="password"` when `secret`, seeded with
`default`). With a single connector, the select is preselected.

*Why not a separate `CreateCompanyDialog`:* the name/country/VAT fields, validation, and
submit plumbing are identical; forking them would duplicate the form logic that
[companies-panel.tsx](../../../frontend/src/components/settings/companies-panel.tsx)
already gets right.

What differs is what the section can change, which follows what the API allows:

| Field | Create | Edit (integration exists) | Edit (none) |
| --- | --- | --- | --- |
| Connector | picker, required | shown, fixed | picker, required |
| Label | — | editable | editable |
| Credentials | inline, seeded with defaults | behind a replace control | inline, seeded |
| Request | `POST /companies` | `PATCH /erp-integrations/{id}` | `POST /erp-integrations` |

### Credentials cannot be edited in place, only replaced wholesale

The API returns **no** credential values — not even non-secret ones like `base_url` — and
`PATCH /erp-integrations/{id}` replaces the stored map in full. So there is no honest way
to render "change just the api_key": the form has nothing to prefill `base_url` from, and
sending a partial map would silently drop the rest.

The edit dialog therefore puts credentials behind an explicit replace control that states
all credentials are replaced, and validates every required field when it is on. Untouched,
no `credentials` key is sent at all and the stored secret is left alone.

*Alternative rejected:* returning non-secret credential fields so they can be prefilled.
That would mean the API deciding per-field what is safe to disclose, and a connector
mislabelling a field would leak it. Write-only for the whole map is the simpler guarantee.

### The connector type is fixed once connected

`PATCH /erp-integrations/{id}` accepts label and credentials only. Switching `erp_type`
would orphan the integration's synced `ErpAccount` rows and its `SyncState`, so it is not
a field edit — it is a disconnect plus a new connection. The dialog shows the type as
static text rather than offering a control the API cannot honour.

### Integration data reaches the panel through one list query

The route fetches `GET /erp-integrations` once (all in-scope companies, no `company_id`
filter) and hands the panel the rows; the dialog picks its company's own. This keeps the
panel presentational — every existing test constructs it from plain props — and avoids a
per-row request.

A company with several integrations edits its **first connected** one and the dialog says
how many others exist. Managing several per company belongs on a dedicated ERP page, not
in a company dialog.

### Company and integration are separate requests on edit

Unlike create, editing touches two resources that already exist, and there is no
compound endpoint. The dialog sends the company `PATCH` first, then the integration
request, and surfaces either failure. A company update that lands while the integration
update fails is visible and re-doable — not silently reported as success.

*Why not add a compound edit endpoint:* it would exist solely to spare the client one
request, and unlike creation there is no orphan-row hazard to justify the coupling.

## Risks / Trade-offs

- **Breaking API change: every existing `POST /companies` caller fails 422.** → The only
  callers are the settings UI and `tests/web_api/test_management.py`, both updated in this
  change. Documented in the proposal and in the spec delta.
- **Existing integration-less companies remain.** → Explicitly allowed; the requirement
  binds at creation. Guarding reads on "has an integration" is out of scope and would
  break current data.
- **A company can now be created that is connected but never verified** (wrong
  credentials, unreachable ERP). → Deliberate: `test-connection` stays a separate,
  explicit action, and the UI can surface it after creation. Blocking creation on a live
  probe would make onboarding depend on ERP availability.
- **Rejecting unknown credential keys could block a future connector's pass-through
  config.** → That connector declares its fields; if genuinely free-form config is ever
  needed, a declared `extra` object field is the escape hatch.
- **`GET /erp-types` leaks which ERP systems the deployment supports.** → It is behind
  authentication and reveals nothing tenant-specific; the same information is already
  implied by the 422 message on an unknown `erp_type`.
- **Test setup: company-create tests now need a valid `integration` block.** → The
  minimal `{"erp_type": "mock"}` requires no encryption key, so the shared `_create`
  helper takes a one-line change; only tests that pass real credentials need the key
  fixture that `test_erp_integrations.py` already establishes.

## Migration Plan

No data migration — no schema change. Deploy order matters only in that the front end
must not ship before the API: an old UI against the new API would get 422 on create.
Ship API and front end together (single repo, single deploy). Rollback is a plain revert;
integrations created by the new path are ordinary `ErpIntegration` rows the old code
already understands.

## Open Questions

- Should the create dialog offer a "Test connection" button before submit? Deferred —
  creation does not depend on it, and it needs an integration id to call the existing
  endpoint. Revisit when a real connector lands.
- Should `refresh-accounts` run automatically after a company is created, so accounts are
  ready for the first sync? Out of scope here; today the sync runner path already handles
  account discovery.
