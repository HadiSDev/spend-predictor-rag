## Why

Every ERP integration so far has been the Debug ERP — a connector that talks to
our own mock server, shaped exactly like the DTOs it has to produce. Nothing has
yet proven the connector interface against an ERP we do not control. Billy
(`billy.dk`) is the first: a Danish SMB accounting system whose customers are
exactly our market, with a documented REST API and a token we already hold.

Billy is also the cheapest place to discover what the interface gets wrong,
because the next two connectors — e-conomic and Business Central — differ from
it in known, specific ways (token lifetime, pagination style, voucher naming).
Building Billy on seams chosen for all three costs little now and saves a
rewrite twice over.

## What Changes

- **New `billy` connector** implementing the full `ErpConnector` contract against
  Billy API v2: chart of accounts, suppliers, GL postings grouped by
  transaction, supplier bills as invoice scans, and attached documents.
- **A shared HTTP connector base** (`HttpErpConnector`) carrying the httpx
  client, status→exception mapping, and bounded retry. Its `_auth_headers()`
  hook is evaluated per request, so a connector whose token expires (Business
  Central) can refresh without changing the interface.
  - **Fixes a live defect**: `MockErpConnector` maps HTTP 429 to `ErpDataError`,
    so the declared `ErpRateLimitError` is raised nowhere in the codebase. The
    shared base raises it, and the mock inherits the correct behaviour.
- **Pluggable pagination** (`PageNumberPaginator`, `SkipPagesPaginator`,
  `NextLinkPaginator`). A connector declares which one it uses; the base drives
  it. Covers Billy's `page`/`pageSize`, e-conomic's `skippages`, and Business
  Central's OData `@odata.nextLink`.
- **Brand metadata in the connector catalog**: a connector may declare
  `brand_slug`, `description` and `docs_url` alongside `display_label`, and
  `GET /erp-types` projects them. Purely additive — a connector that declares
  none is unchanged.
- **A branded ERP picker in Settings**: the plain `Select` in the company
  create/connect form becomes a card grid — vendored logo, label, one-line
  description — driven entirely by the catalog, so it stays true for connectors
  added later with no front-end change.
- **No change to the `ErpConnector` method contract.** Billy's postings
  reference their transaction, never a bill line, which is exactly the shape the
  model already expects: an entry links to its invoice scan through the voucher,
  and `source_line_erp_id` is null. That holds for e-conomic and Business
  Central too.

Not in scope: the e-conomic and Business Central connectors themselves. This
change builds the seams they need and documents how each maps onto them; it does
not implement them.

## Capabilities

### New Capabilities

- `billy-erp-connector`: how the `billy` connector authenticates against Billy
  API v2 and maps its accounts, contacts, transactions, postings, bills and
  attachments onto the normalized connector DTOs — including which Billy field
  is authoritative for a voucher id, how an entry type is derived from a
  transaction's originator, and why account selection is applied client-side.

### Modified Capabilities

- `erp-connector-interface`: adds the shared HTTP base and its per-request
  `_auth_headers()` hook, the pagination strategy seam, the corrected
  `ErpRateLimitError` mapping, and optional brand metadata on a connector class.
  The abstract method signatures are unchanged.
- `web-api-erp-integration-management`: `GET /erp-types` gains the optional
  `brand_slug`, `description` and `docs_url` fields on each catalog entry.
- `frontend-settings`: the ERP-system chooser in the company create/connect form
  is specified as a branded card grid rather than a dropdown.

## Impact

**Backend**

- New: `src/web_api/connectors/http.py`, `src/web_api/connectors/pagination.py`,
  `src/web_api/connectors/billy.py`.
- Modified: `src/web_api/connectors/base.py` (brand metadata fields on
  `ErpConnector`), `src/web_api/connectors/__init__.py` (register `billy`),
  `src/web_api/connectors/mock.py` (rebased on `HttpErpConnector`; behaviour
  unchanged except 429 → `ErpRateLimitError`),
  `src/web_api/schemas.py` (`ErpTypeRead`),
  `src/web_api/routers/erp_integrations.py` (project the new fields).
- Unchanged by design: `ai_api/sync/runner.py`, the ORM, and every migration.
  A new `erp_type` needs no schema change — the integration row already stores
  it as a string and its credentials as an encrypted map.

**Frontend**

- New: `src/assets/erp/` (vendored logos, `README.md` recording provenance),
  `src/components/settings/erp-brand-mark.tsx`.
- Modified: `src/components/settings/companies-panel.tsx` (card grid),
  `src/lib/types.ts` (`ErpTypeRead`).

**Operational**

- Billy credentials are stored through the existing encrypted-credential path,
  so a deployment connecting Billy must have `WEB_API_CREDENTIAL_ENC_KEY` set —
  unlike the Debug ERP, whose fields all have defaults.
- Outbound network access to `api.billysbilling.com` is required by the sync
  runner and by `POST /erp-integrations/{id}/test-connection`.

**Risk**

Three details are read from Billy's published documentation and not yet
verified against the live API: the serialization of a transaction's `originator`
reference, whether `/transactions` honours `minEntryDate`/`maxEntryDate`, and
whether a file's `downloadUrl` is a signed URL on another host. The change
sequences a live spike before the connector body so these are settled by
observation rather than assumption.
