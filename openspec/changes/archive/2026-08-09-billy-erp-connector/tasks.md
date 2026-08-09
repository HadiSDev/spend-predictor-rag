## 1. Live spike — settle the three unverified behaviours

The connector body depends on answers the documentation does not give. Do this
first; the fixtures for every later test come out of it.

- [x] 1.1 Add `scripts/billy_spike.py` — a throwaway read-only script driven by
      `BILLY_ACCESS_TOKEN` from the environment, never from a committed file.
- [x] 1.2 Confirm the auth handshake: `X-Access-Token` against the organization
      endpoint, and record the organization id it returns.
- [x] 1.3 Record a transaction listing **with postings embedded** and determine
      the exact serialization of the `originator` reference — the field names
      and how the originator's kind (bill / bank payment / daybook transaction /
      sales invoice) is expressed.
- [x] 1.4 Determine whether `/transactions` honours `minEntryDate` /
      `maxEntryDate`. If it does not, record whether it can be sorted by
      `entryDate` descending, since that is the fallback incremental strategy.
- [x] 1.5 Survey the originator kinds present in the real organization's
      transactions and check them against the derivation table in `design.md`.
- [x] 1.6 Fetch a bill with `include=bill.lines`, and follow one attachment to
      its file. Record whether `downloadUrl` is on the Billy API host or a
      signed URL elsewhere, and whether it accepts (or rejects) the auth header.
- [x] 1.7 Save the captured JSON responses as test fixtures under
      `tests/fixtures/billy/`, scrubbed of any real supplier names, CVR numbers
      and amounts.
- [x] 1.8 Update `design.md` — replace each of the four Open Questions with what
      was observed, and amend the entry-type table and the incremental strategy
      if the spike contradicts them.

## 2. Shared HTTP base and pagination

Ship this with the mock rebased and the suite green **before** writing Billy, so
a Debug-ERP regression can only have come from this step.

- [x] 2.1 Add `src/web_api/connectors/pagination.py`: a `Paginator` protocol
      with `PageNumberPaginator`, `SkipPagesPaginator` and `NextLinkPaginator`.
      Lift `PageNumberPaginator` from the loop already in `mock.py:_paginate`.
- [x] 2.2 Add `src/web_api/connectors/http.py`: `HttpErpConnector` with the
      httpx client, an injectable `_http`, the `_auth_headers()` hook evaluated
      per request, `_get`, `_paginate` (driving the declared paginator) and
      `_request_raw` for binary.
- [x] 2.3 Map statuses in the base: 401/403 → `ErpAuthError`, 429 →
      `ErpRateLimitError` (with `retry_after` when the header supplies one),
      5xx and transport failure → `ErpConnectionError`, anything else →
      `ErpDataError`. Add bounded retry with backoff on 429 and 5xx.
- [x] 2.4 Give `ErpRateLimitError` a `retry_after` attribute in `base.py`.
- [x] 2.5 Rebase `MockErpConnector` on `HttpErpConnector`, deleting its private
      HTTP and pagination code. Its field mapping is untouched.
- [x] 2.6 Run `uv run pytest tests/test_connectors.py tests/test_sync_runner.py`
      and confirm green — this is the regression check for the Debug ERP.
- [x] 2.7 Add base tests: per-request auth re-evaluation, each status mapping,
      a 503-then-success retry, a 429 that exhausts retries, and cursor paging
      stopping on an absent next-link.
- [x] 2.8 Assert the fixed defect explicitly: the mock connector now raises
      `ErpRateLimitError` on HTTP 429, where it previously raised
      `ErpDataError`.

## 3. Brand metadata through the catalog

- [x] 3.1 Add optional `brand_slug`, `description` and `docs_url` class
      attributes to `ErpConnector` in `base.py`, defaulting to absent.
- [x] 3.2 Extend `ErpTypeRead` in `src/web_api/schemas.py` with the three
      optional fields.
- [x] 3.3 Project them in `list_erp_types`
      (`src/web_api/routers/erp_integrations.py`).
- [x] 3.4 Test that a connector declaring no brand metadata produces the same
      catalog entry as before, so no existing client is affected.

## 4. The Billy connector

- [x] 4.1 Create `src/web_api/connectors/billy.py` with `BillyConnector`
      deriving from `HttpErpConnector` and declaring `PageNumberPaginator`,
      `display_label = "Billy"`, and its brand metadata.
- [x] 4.2 Declare `credential_fields`: `access_token` (required, secret),
      `organization_id` (optional), `base_url` (optional, default
      `https://api.billysbilling.com/v2`). No email/password field.
- [x] 4.3 Implement `_auth_headers()`, `authorize()` (resolve and cache the
      organization id, honouring a supplied override) and `test_connection()`.
- [x] 4.4 Implement `fetch_accounts()`: `accountNo` → code, `natureId` → type
      (it is already the semantic string), `!isArchived` → `is_active`,
      `taxRateId` present → `with_vat`, `parent_code` null. Build and cache the
      `accountId → accountNo` map here; postings and bill lines both need it.
- [x] 4.5 Implement `fetch_vendors()`: supplier contacts only, `registrationNo`
      → `vat_number`, `countryId` → `country_code`.
- [x] 4.6 Implement `fetch_entries()`: page `/transactions` sorted
      `entryDate DESC` with `include=transaction.postings:embed`, stopping once
      entries predate `since` — **the date filters are accepted and ignored, so
      they must not be used**. Flatten one entry per posting, `voucher_id` =
      transaction id, `side` → debit or credit, `source_line_erp_id` always null.
- [x] 4.7 Skip both halves of a void pair (`isVoid` and `isVoided`), so totals
      are unchanged and each bill is reachable from exactly one voucher.
- [x] 4.8 Resolve each posting's `accountId` to its account number, dropping a
      posting whose account is unknown with a warning rather than storing an
      empty code.
- [x] 4.9 Implement the entry-type derivation over the `"kind:id"` prefix of
      `originatorReference` (**not** `originatorType`, which is null), covering
      `bill`/`credit_note`/`bankPayment`/`salesTaxPayment`/`daybookTransaction`/
      `salesTaxReturn`, the sales-invoice skip, and the `journal_entry` fallback
      logged once per unrecognised kind.
- [x] 4.10 Apply the `account_codes` filter client-side after flattening, with an
      empty set short-circuiting before any request.
- [x] 4.11 Implement `fetch_invoice_scan()`: resolve transaction → originating
      bill id from `originatorReference` → `GET /bills/{id}?include=bill.lines`
      (response is `bill` singular plus a sideloaded `billLines`); return null
      for a non-bill voucher; carry the requested transaction id back as
      `voucher_id`; fall back `suppliersInvoiceNo` → `voucherNo` → bill id for
      `invoice_number`; map lines via `accountId`. Memoize per sync.
- [x] 4.12 Implement `fetch_invoice_document()`: find the attachment whose
      `ownerReference` is `bill:<id>` → `GET /files/{fileId}` → fetch
      `downloadUrl`; filename from the file record (the download carries no
      content-disposition); null when nothing is attached; `ErpConnectionError`
      on a failed fetch; **no auth header when the download host differs from
      `base_url`'s** — Billy's S3 accepts the header, so nothing else catches it.
- [x] 4.13 Register `billy` in `src/web_api/connectors/__init__.py`.

## 5. Billy tests

All fixture-based against an injected transport. No test may touch the network.

- [x] 5.1 `tests/test_billy_connector.py` scaffolding: a connector fixture whose
      `_http` is an `httpx.MockTransport` client served from the scrubbed
      captures in `tests/fixtures/billy/`.
- [x] 5.2 Auth: token header present on every request; organization discovered
      when no `organization_id` credential is given; supplied id overrides;
      401 → `ErpAuthError`.
- [x] 5.3 Accounts: archived → inactive, `taxRateId` → `with_vat`, `natureId`
      becomes the type, group does not become `parent_code`.
- [x] 5.4 Vendors: customer-only contacts excluded; `registrationNo` becomes
      `vat_number`.
- [x] 5.5 Entries: postings of one transaction share the transaction id as
      `voucher_id`; the many transactions whose `voucherNo` is null or `""` do
      **not** collide; `source_line_erp_id` is null on every entry; credit
      `side` fills only `credit_amount`.
- [x] 5.6 Entry types: one test per row of the derivation table — including
      `salesTaxPayment` → `payment`, `salesTaxReturn` → `journal_entry`, the
      sales-invoice skip, the unknown-originator fallback, and that a null
      `originatorType` beside a populated `originatorReference` still resolves.
- [x] 5.7 Voids: neither half of a void pair yields entries, and the bill they
      reference is reachable from exactly one voucher.
- [x] 5.8 Account ids: a posting's `accountId` becomes the account number; a
      posting on an unknown account is dropped rather than stored blank.
- [x] 5.9 Watermark: `since` stops the sorted scan early and returns only newer
      entries; no `since` reads everything; assert the request carries the
      **sort** parameters and **not** `minEntryDate`, since Billy ignores it.
- [x] 5.10 Account filter: unselected accounts dropped; empty set issues no
      request (assert on the transport, not just the empty result).
- [x] 5.11 Invoice scan: payment voucher → null; returned `voucher_id` equals the
      argument; the real fixture's null `suppliersInvoiceNo` and `""` `voucherNo`
      fall through to the bill id; sideloaded `billLines` map with their own ids
      and resolved account numbers; a second lookup issues no new request.
- [x] 5.12 Documents: no attachment → null; server error → `ErpConnectionError`;
      the off-host S3 download is fetched with **no** `X-Access-Token` header;
      the filename comes from the file record.
- [x] 5.13 Catalog: `GET /api/v1/erp-types` includes `billy` with its brand
      metadata and credential descriptors, and `access_token` is marked secret.
- [x] 5.14 Integration creation: a `billy` company creation succeeds with an
      `access_token`, is rejected without one, and is rejected when a `password`
      key is supplied.

## 6. Frontend — branded connector chooser

- [x] 6.1 Add `frontend/src/assets/erp/` with `billy.svg`, `mock.svg`, and a
      `README.md` recording each file's source URL and provenance, mirroring
      `src/assets/flags/README.md`.
- [x] 6.2 Add `frontend/src/components/settings/erp-brand-mark.tsx`, mirroring
      `country-flag.tsx`: `import.meta.glob` resolution so a missing asset is a
      build-visible gap, and a deliberate lettered-tile fallback.
- [x] 6.3 Add `brand_slug`, `description` and `docs_url` to `ErpTypeRead` in
      `frontend/src/lib/types.ts`.
- [x] 6.4 Replace the `erp_type` `Select` in `companies-panel.tsx` with a card
      grid: mark, label, description when present, distinct selected state,
      keyboard operable and labelled for screen readers. Keep the reseeding of
      credential defaults, the single-connector preselect, and the required-field
      validation.
- [x] 6.5 Leave the credential inputs, the edit-mode credential-replacement
      flow, and the fixed `erp_type` rule untouched, and confirm by running the
      existing `companies-panel.test.tsx` unchanged.
- [x] 6.6 Add `erp-brand-mark.test.tsx`: artwork renders for a known slug, the
      lettered tile renders for an unknown slug and for a missing `brand_slug`.
- [x] 6.7 Extend `companies-panel.test.tsx`: cards render from the catalog, an
      unseen connector renders with the same treatment as the others, selecting
      a card reseeds the credential fields, keyboard selection works, and submit
      still sends one `POST /api/v1/companies`.

## 7. End-to-end verification against the real Billy organization

- [x] 7.1 Create a company in Settings against the real Billy organization
      through the new card grid, and confirm the credential is stored encrypted
      and never returned.
- [x] 7.2 Run `POST /erp-integrations/{id}/test-connection` and
      `refresh-accounts`, and confirm the chart of accounts appears with
      `with_vat` seeded and `sync_enabled` left to the customer.
- [x] 7.3 Enable a few accounts and run `python -m ai_api.sync.runner
      --integration-id <id>`. Confirm entries, invoices and lines land, that
      entries link to their invoice through the voucher, and that the watermark
      advances.
- [x] 7.4 Check `GET /erp-entries/vouchers` for the company: a voucher's
      postings stay together, `payment` entries are excluded from the listing,
      and `source_invoice_line_id` is null throughout as specified.
- [x] 7.5 Open one invoice's document through
      `GET /invoices/{id}/document` and confirm the Billy attachment streams.
- [ ] 7.6 Record the wall-clock cost of the sync and the number of transactions
      fetched versus postings kept, so decision 6's client-side filtering cost is
      measured rather than assumed. **Not measured** — the connector still scans
      `/transactions` sorted by `entryDate DESC`, so decision 6's cost remains
      assumed, not proven. Revisit if a customer's sync gets slow: `/postings`
      and `/bills` do honour date filters and are the escape hatch.

## 8. Documentation

- [x] 8.1 Update `CLAUDE.md`: Billy in the connector list, the shared HTTP base
      and pagination seam, the brand metadata on `/erp-types`, and the note that
      a Billy deployment requires `WEB_API_CREDENTIAL_ENC_KEY` and outbound
      access to `api.billysbilling.com`.
- [x] 8.2 Add `BILLY_ACCESS_TOKEN` (spike/smoke only) to `.env.example` with a
      comment that runtime credentials come from the integration row, not the
      environment.
- [x] 8.3 Delete `scripts/billy_spike.py`, or reduce it to the opt-in smoke
      check — it must never run under `uv run pytest`.
