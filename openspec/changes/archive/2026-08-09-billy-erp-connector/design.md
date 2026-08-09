## Context

`ErpConnector` (`src/web_api/connectors/base.py`) has exactly one implementation:
`MockErpConnector`, which talks to `mock_erp/` — a server we wrote to emit the
DTOs the connector consumes. The interface has therefore never been tested
against a system that disagrees with it.

Billy is the first real one. It is a Danish SMB accounting product, its API is
documented at `https://www.billy.dk/api` (v2, `https://api.billysbilling.com/v2`),
and we hold a working access token. Two more connectors follow — e-conomic and
Business Central — and their differences from Billy are already known:

| Concern | Billy | e-conomic | Business Central |
| --- | --- | --- | --- |
| Auth | static `X-Access-Token` | static `X-AppSecretToken` + `X-AgreementGrantToken` | OAuth2 client credentials; **bearer token expires** |
| Pagination | `page` / `pageSize`, response carries a total | `skippages` / `pagesize`, response carries `nextPage` | OData `@odata.nextLink` cursor |
| Voucher identity | `transaction` (id + `voucherNo`) | `voucherNumber` | `documentNumber` |
| Entry type | derived from `transaction.originator` | entry `type` field | `documentType` |
| Rate limiting | 429 | 429, documented | 429 with `Retry-After` |

Constraints that shape the design:

- **`ai_api` imports `web_api`, never the reverse.** Connectors live in
  `web_api/connectors/`; the sync runner in `ai_api` consumes them
  polymorphically and must not learn that Billy exists.
- **A new `erp_type` requires no schema change.** `ErpIntegration.erp_type` is a
  string and credentials are an encrypted map, so registering a connector is the
  whole of the backend wiring.
- **The frontend picker is catalog-driven** (`frontend/src/lib/erp-types.ts` →
  `GET /erp-types`), so Billy appears in it with no front-end change. The
  branded card in this change is a deliberate upgrade of that picker, not a
  requirement of adding a connector.
- **Entries join invoices through the voucher.** `_persist_entries` builds its
  link from `voucher_invoice_map`. Billy's postings carry a transaction, not a
  bill line, and that is the shape the model already assumes.

## Goals / Non-Goals

**Goals:**

- A `billy` connector that satisfies all seven `ErpConnector` methods against
  the live Billy API, and syncs a real Billy organization end to end through the
  existing runner.
- Extract the plumbing all three planned connectors need — HTTP client, error
  mapping, retry, pagination — into shared code, with the variation behind named
  seams rather than per-connector copies.
- Make the connector catalog rich enough to render a branded chooser, without
  the frontend knowing any connector by name.
- Settle, by observation against the live API, the three Billy behaviours the
  documentation leaves ambiguous.

**Non-Goals:**

- Implementing the e-conomic or Business Central connectors. This change proves
  the seams fit them; it does not use them.
- OAuth token refresh machinery. The `_auth_headers()` hook is the place it will
  go; Billy needs none, so none is written.
- Any change to `ErpConnector`'s abstract method signatures, the ORM, the sync
  runner, or the reporting layer.
- Writing to Billy. Every call this connector makes is a read.

## Decisions

### 1. `HttpErpConnector` as a shared base, with a per-request auth hook

A new `web_api/connectors/http.py` owns the httpx client, header assembly,
status→exception mapping, bounded retry, and binary fetch. Subclasses implement
`_auth_headers() -> dict[str, str]` and declare a paginator.

The hook is called **per request**, not once at `authorize()`. That single
choice is what lets Business Central refresh an expired bearer token later
without touching the abstract interface or any caller: `_auth_headers()` becomes
`_ensure_token()`-then-return, and everything above it is unchanged. Billy's
implementation is a one-line dict.

*Alternative considered — a `requests`/httpx mixin per connector, i.e. today's
copy in `mock.py` duplicated twice more.* Rejected: the error mapping is the
part most likely to be got wrong, and three copies means three chances. The
existing copy already demonstrates this — see decision 2.

*Alternative considered — a generic `HttpClient` collaborator injected into each
connector rather than a base class.* Marginally cleaner for testing, but the
existing tests already inject via `connector._http` (commit `0285bf9`), and a
base class keeps `_get`/`_paginate` as the terse call sites the mappers want.

### 2. The shared base raises `ErpRateLimitError`, fixing a real defect

`base.py` declares `ErpRateLimitError` and `mock.py:70` maps HTTP 429 to
`ErpDataError`. Nothing in the codebase raises the rate-limit error, so no caller
can distinguish "back off and retry" from "the ERP sent us nonsense". The shared
base maps 429 → `ErpRateLimitError` (carrying `retry_after` parsed from the
header when present), and the mock inherits it.

The base retries a 429 or 5xx a bounded number of times with backoff before
letting the error escape. Beyond that it raises, and the runner's existing
per-integration isolation records the failure on that integration's `SyncState`
and continues with the next one — which is the correct outcome for a
rate-limited tenant.

### 3. Pagination as a declared strategy, not an if-tree

`web_api/connectors/pagination.py` defines a small `Paginator` protocol with
three implementations: `PageNumberPaginator` (Billy — `page`/`pageSize`, stop
when the accumulated count reaches the reported total),
`SkipPagesPaginator` (e-conomic), `NextLinkPaginator` (Business Central OData).
A connector sets `paginator = PageNumberPaginator(...)`; the base's
`_paginate(path, **params)` returns the flat list of items.

The mock's current loop is exactly `PageNumberPaginator`, so it moves over with
no behaviour change — which is also how we know the abstraction is not invented:
it is the shape already in the tree.

### 4. `voucher_id` is Billy's transaction **id**, not its `voucherNo`

A Billy `Transaction` has both. `voucherNo` is the human-facing number printed
on the voucher; it is per-daybook and per-fiscal-year, so it repeats. The `id` is
a stable global key.

`ErpEntry.voucher_id` is a join key — `_persist_entries` uses it to find the
invoice `_persist_invoices` wrote — so it must be unique or entries from
different years silently attach to the wrong invoice. We use the transaction id
and surface `voucherNo` in `raw` for display later.

*Trade-off:* the id is an opaque string, so a user comparing our UI against
Billy's sees no shared number. Accepted; correctness of the join outranks
recognisability, and `voucherNo` remains available for the UI to show.

**Confirmed by the spike, more starkly than expected.** Across 95 transactions
in a real organization, `voucherNo` was `null` on 37 and `""` on 10 — half the
ledger shares one of two "values" — and of the rest, `"4"`, `"5"`, `"6"`, `"9"`,
`"11"`, `"12"`, `"16"`, `"17"`, `"18"` and `"19"` each appeared three times.
Keying on it would have collapsed unrelated vouchers into single groups on the
first real sync.

### 5. Entries come from `/transactions` with embedded postings, not `/postings`

`GET /postings` returns individual postings carrying only a `transactionId`,
which would need a second lookup per transaction to learn the entry type.
`include=transaction.postings:embed` is confirmed working, so the connector
lists `/transactions` and flattens each transaction's postings into
`ErpEntryData`: one request per page yields the voucher grouping *and* the
originator, and it matches how `_sync_one` regroups entries into vouchers
anyway.

**The originator is a `"type:id"` string in `originatorReference`.** This is the
spike's most important correction. Billy also has an `originatorType` field, and
it was `null` on all 95 transactions observed — reading it, as the documentation
implies, would have made every transaction fall to the default. The kind is the
prefix of `originatorReference`, e.g. `"bill:aQeuEclyS4atj4WvItwS3A"`, and the
suffix is the id `fetch_invoice_scan` resolves the bill from.

**Entry type derivation**, from that prefix:

| Originator prefix | `entry_type` | Seen in the live org |
| --- | --- | --- |
| `bill` without `creditedBillId` | `purchase_invoice` | 49 |
| `bill` with `creditedBillId` set | `credit_note` | — |
| `bankPayment` | `payment` | 34 |
| `salesTaxPayment` | `payment` | 2 |
| `daybookTransaction` | `journal_entry` | 5 |
| `salesTaxReturn` | `journal_entry` | 4 |
| `invoice` (a sales invoice) | skipped — this is a spend tool | 1 |
| anything else / absent | `journal_entry` | — |

`salesTaxPayment` and `salesTaxReturn` were **not** in the pre-spike table and
are 6% of this organization's ledger. A VAT payment settles a liability exactly
as a bank payment does, so it is a `payment`; the periodic VAT settlement is a
`journal_entry`. Both would have landed on the fallback and been merely
mislabelled rather than lost, which is the fallback earning its place.

The fallback stays `journal_entry` rather than an error: an unrecognised
originator still moved money through a selected account, and dropping it would
understate spend. Unknown prefixes are logged once per sync so a new Billy
feature shows up as a log line rather than a silent gap.

### 5b. Postings name their account by id, so the connector maps it

A posting carries `accountId`, not `accountNo`, while `ErpEntryData.
erp_account_code` is the account *number* the rest of the system keys on —
`ErpAccount.erp_account_code`, the `sync_enabled` selection, and the reports all
use it.

`fetch_accounts()` already retrieves every account, so the connector builds an
`accountId → accountNo` map there and reuses it when mapping postings and bill
lines. `fetch_entries` therefore fetches the chart first if it has not already;
this costs one extra request on a cold call and none during a sync, where
`_sync_one` calls `fetch_accounts()` before `fetch_entries()` regardless.

A posting whose `accountId` is absent from the map is dropped with a warning
rather than stored under an empty code: an entry with no resolvable account
cannot be filtered, reported or reconciled, and a blank code would silently
pollute every per-account total.

*Bonus finding:* `natureId` is itself the semantic string (`expense`, `asset`,
`liability`, `revenue`, `equity`), so `erp_account_type` needs no second request
to `/accountNatures` and no `include=` sideload.

### 5c. Voided transactions are skipped, both halves

Billy voids a transaction by leaving the original in place with
`isVoided: true` and adding a reversal with `isVoid: true`. In the live
organization that is 16 pairs out of 95 transactions — a third of the ledger.

The connector skips both halves. Three reasons, in order of weight:

1. **It keeps the bill↔voucher relation one-to-one.** Measured on the live org:
   **zero** bills are referenced by more than one *live* transaction, but **12**
   are once voided ones are counted. Since `fetch_invoice_scan` resolves a
   voucher to its bill, keeping voided transactions would hand `_persist_invoices`
   the same bill under two different voucher ids and duplicate the invoice.
2. A void pair nets to zero, so excluding both leaves every total unchanged.
3. Billy's own reports treat a voided transaction as cancelled, so excluding it
   is what makes our figures agree with the customer's own books.

*Alternative considered — keep both halves and let them net.* Totals would agree
but the invoice layer would not, per (1). *Alternative considered — keep the
original and drop the reversal.* That would count cancelled spend as real.

### 6. `/transactions` ignores date filters, so `since` is a sorted early stop

The spike's second correction. `/transactions` accepts `minEntryDate`,
`entryDate`, `minDate` and `period` without complaint and **ignores all four**:
each returned the full 95 rows, including a `minEntryDate` of `2099-01-01`. A
connector that trusted the documented filter would have re-fetched the entire
ledger on every sync while appearing to honour the watermark.

`sortProperty=entryDate&sortDirection=DESC` **is** honoured, so the connector
pages transactions newest-first and stops at the first page whose entries all
predate `since`. Cost is proportional to what has changed, which is what the
watermark is for. With no `since` it pages to the end, as a backfill should.

*Alternative considered — `/postings`, which does filter.* Verified in the
spike: `/postings?minEntryDate=2099-01-01` returns 0 of 241, and
`?accountId=…` returns 2 of 241. Both server-side filters work there and neither
works on `/transactions`. It was rejected anyway because a posting carries no
originator, so entry types would need a second pass over transactions — and that
pass has no working date filter either, putting us back here. Recorded because
it is the escape hatch if a large organization makes the sorted scan too slow:
postings for the date window, plus transactions resolved by id for their types.

*Alternative considered — `/bills?minEntryDate=…`, which also filters
correctly (26 → 0 for a future bound).* It bounds only the invoice half of the
ledger; journal entries and payments have no bill, so it cannot drive the entry
sync on its own.

### 6b. Account selection is filtered client-side, and we say so

`fetch_entries(account_codes=...)` is a fetch-time gate elsewhere — the mock
passes it to the server. Since entries come from `/transactions` (decision 5),
which has no account filter, the connector drops postings whose account is not
selected after flattening.

The contract is preserved exactly (`None` → all, empty set → nothing, non-empty
→ that subset), and the empty-set case still short-circuits before any request.
What is not preserved is the *cost*: Billy pulls every transaction in the date
window regardless of how few accounts are enabled. This is stated in the spec
rather than hidden, because it is the difference between a cheap incremental
sync and an expensive one, and it is the first thing to revisit if Billy syncs
are slow — with the `/postings` route in decision 6 as the measured alternative.

### 7. Bills are fetched per voucher, with a cache

`fetch_invoice_scan(voucher_id)` resolves the transaction → its originator bill
id → `GET /bills/{id}?include=bill.lines`. The runner calls this once per
invoice-bearing voucher, so the connector memoizes the transaction→bill mapping
built during `fetch_entries` and caches fetched bills, exactly as
`MockErpConnector._invoice_by_voucher` does.

**Lines sideload, they do not nest.** The response is
`{"bill": {...}, "billLines": [...], "meta": {...}}` — note `bill` singular for
a by-id fetch, where a list fetch returns `bills`. Lines are joined to their
bill by `billLine.billId` (the bill also carries `lineIds`), and a bill line
names its account by `accountId`, mapped through decision 5b like a posting.

Field mapping: `invoice_number` = `suppliersInvoiceNo`, falling back to
`voucherNo` and then the bill id; `invoice_date` = `entryDate`;
`total` = `grossAmount`; `tax` = `tax`; `currency` = `currencyId` (Billy
currency ids are the ISO code); `line_erp_id` = the bill line's id;
`native_account_code` = the line's account, mapped from `accountId`.

The fallback chain is not hypothetical: the first real bill the spike fetched
had `suppliersInvoiceNo: null` **and** `voucherNo: ""`, so it lands on the bill
id. A connector that assumed either field was populated would have written a
blank invoice number on real data.

`taxMode` is carried in `raw` and not acted on. It says whether line amounts are
VAT-inclusive (`"incl"` on the observed bill), which matters for reconciling a
line against its postings — but `ErpInvoiceLineData.amount` is defined as what
the ERP states for the line, and reinterpreting it here would put a number in
the ledger that Billy never showed the customer. The existing `with_vat`
machinery on the account is where that concern already lives.

`source_line_erp_id` on every entry is **null**. Billy postings reference their
transaction, never a bill line. Deriving the link by matching account and amount
was considered and rejected: `ErpEntry.source_invoice_line_id` is specified as
derived, never matched, and a heuristic link would put a wrong spend category on
a real posting with no way for a user to see that it was guessed.

### 7b. The document lives on S3, and must be fetched without our credential

Confirmed: a file's `downloadUrl` points at
`billysbilling-eu.s3.eu-north-1.amazonaws.com`, not at the Billy API host. It
returns the PDF with **or** without `X-Access-Token` (200 either way,
`content-type: application/pdf`), which is the dangerous case — sending the
credential would work, so nothing would ever fail to reveal that we were handing
a Billy access token to AWS on every document fetch.

The connector compares the download host against the configured `base_url` host
and omits the auth header when they differ. The pre-spike design guessed this
was a risk; it is real, and the guard is what stops it.

Resolution path, also confirmed: attachments are **not** embedded in a bill.
They are their own resource carrying `ownerReference: "bill:<id>"` and a
`fileId`, so the connector lists attachments for the bill, then
`GET /files/{fileId}` for the `downloadUrl`. The file record also supplies
`fileName` and `isPdf`, so the document's name comes from Billy rather than
being invented — the S3 response carries no `content-disposition`.

### 8. Credentials: access token only

Billy supports HTTP Basic with an account's email and password as well as
`X-Access-Token`. The connector declares only the token.

A user's password grants full account access, cannot be scoped, and cannot be
revoked without a password change; an access token is revocable in Billy's UI
and is what their docs recommend for integrations. Declaring only the token also
means `credential_fields` validation rejects a password if anyone tries.

Fields: `access_token` (required, secret), `organization_id` (optional),
`base_url` (optional, defaults to `https://api.billysbilling.com/v2`).

`organization_id` is optional because a Billy token is already bound to one
organization: `authorize()` calls `GET /organization` and caches the id it gets
back, and only uses a supplied value to override. This keeps the connect form to
one field a user must find, which is the difference between a five-minute setup
and a support ticket.

### 9. Brand metadata on the connector class

`ErpConnector` gains three optional class attributes — `brand_slug`,
`description`, `docs_url` — projected by `GET /erp-types`. A connector that
declares none produces the same payload as today, so the field additions are
backward compatible for any existing client.

The frontend must not know connector names. Putting the brand key *in the
catalog* is what keeps the card grid generic: the logo lookup is
`brand_slug → src/assets/erp/<slug>.svg`, with a lettered fallback tile for a
connector whose artwork we do not have. That mirrors `CountryFlag`, which faces
the identical problem (31 flags, 249 countries) and solves it the same way.

*Alternative considered — a static brand map in the frontend.* Rejected: it
reintroduces the per-connector front-end change that the catalog exists to
avoid, and it would drift from the backend catalog silently.

### 10. The picker becomes a card grid

The current chooser is a `Select` whose options are label strings. With one
connector that is adequate; with three it is the moment a user decides whether
this product supports their accounting system, and a dropdown of text answers
that question worse than a row of logos.

The grid replaces only the `erp_type` field. The credential inputs below it are
already rendered from `credential_fields` and are untouched, so Billy's three
fields render themselves. Edit mode is likewise untouched — `erp_type` is fixed
once connected, so there is no picker to restyle there.

## Risks / Trade-offs

- **[RESOLVED — the `originator` reference's shape]** → it is a `"type:id"`
  string in `originatorReference`, and the `originatorType` field the docs imply
  is null throughout (decision 5). The derivation lives in one small function
  with the raw payload preserved in `raw`.

- **[RESOLVED — `/transactions` ignores date filters]** → it does, silently, for
  all four candidate spellings. The watermark is an early stop on an
  `entryDate DESC` scan instead (decision 6).

- **[RESOLVED — `downloadUrl` is off-host and accepts our credential]** → it is
  an S3 URL that returns 200 with or without `X-Access-Token`, so nothing would
  have failed to reveal the leak. The host comparison guard is load-bearing
  (decision 7b).

- **[Billy fetches all transactions in the window regardless of account
  selection]** → decision 6b. Accepted; the measured alternative is the
  `/postings` route, whose server-side `accountId` and `minEntryDate` filters
  the spike verified work. Not built speculatively, and task 7.6 measures
  whether it is needed.

- **[A posting could be dated inside the window while its transaction is dated
  outside it]** → the sorted early stop would miss it. Not observed, but not
  disproved either; open question 1, with a lookback margin as the fix.

- **[Rebasing `MockErpConnector` on the shared base could regress the Debug
  ERP]** → it is the only connector any existing test exercises, so the existing
  suite is the regression test. The rebase is a separate task, run green before
  Billy is written, and its one intended behaviour change (429) is asserted
  explicitly.

- **[Live-API tests would be flaky and need a secret in CI]** → the committed
  test suite is fixture-based against an injected `httpx.MockTransport`, with the
  fixtures captured from the spike so they are shaped like real responses rather
  than like our DTOs. The live smoke script is opt-in via an env var and is never
  part of `uv run pytest`'s default run.

- **[Vendored logo licensing]** → third-party marks are used nominatively to
  identify the integration, which is ordinary for an integrations page, but the
  provenance and source URL of each file are recorded in
  `src/assets/erp/README.md` (as the flags directory already does) so the
  origin of every asset is auditable.

## Migration Plan

No data migration. The change is additive:

1. Ship the shared base and pagination with the mock rebased; the existing suite
   proves the Debug ERP is unchanged.
2. Ship the catalog fields; older clients ignore unknown JSON keys, and the
   frontend renders a fallback tile for any connector without a `brand_slug`.
3. Ship the `billy` connector. It becomes selectable the moment it is registered
   — no migration, no flag.

**Rollback**: unregister `billy` in `connectors/__init__.py`. Existing Billy
integration rows persist and simply fail their next sync with "Unknown
connector", which the runner already isolates per integration. Nothing else in
the system needs to be reverted.

## Resolved by the spike

All four pre-implementation questions were settled by observation against a live
Billy organization (95 transactions, 241 postings, 26 bills, 98 accounts).

1. **Does `/transactions` accept `minEntryDate`/`maxEntryDate`?** **No** — it
   accepts and ignores them, and three other candidate spellings besides. Sorting
   by `entryDate DESC` is honoured, so the watermark is an early stop on a
   sorted scan (decision 6). `/postings` and `/bills` *do* filter by date, and
   are recorded as the escape hatch.
2. **Is `downloadUrl` same-host or signed off-host?** **Off-host** (AWS S3), and
   it accepts our credential rather than rejecting it — so the guard omitting
   the auth header for a foreign host is load-bearing, not defensive
   (decision 7b).
3. **Does Billy return an originator kind we have not enumerated?** **Yes, two**
   — `salesTaxPayment` and `salesTaxReturn`, 6% of the ledger, now mapped
   (decision 5). And the kind is read from `originatorReference`, not the
   `originatorType` field the docs imply, which was null throughout.
4. **Should a sales `invoice` originator be skipped or stored?** Skipped, as
   designed — the product is a spend tool and revenue postings are noise, the
   same reasoning that excludes `payment` from the entry listings. One such
   transaction existed in the live org. Worth revisiting only if a customer
   needs net position rather than spend.

## Open Questions

1. **Does a posting's `entryDate` always equal its transaction's?** It did on
   every row observed, and the sorted early stop (decision 6) assumes it: a
   posting dated inside the window whose transaction is dated outside it would
   be missed. If Billy permits them to diverge, the fix is a lookback margin on
   the transaction scan. Worth a check against a larger organization.
2. **How does the sorted scan behave at scale?** 95 transactions is not a test
   of it. Task 7.6 measures the real cost, and decision 6 records the
   `/postings` alternative to switch to if it is bad.
3. **Are `salesTaxReturn` postings genuinely spend-neutral?** They are mapped to
   `journal_entry`, which the entry listings *include*. If VAT settlement rows
   turn out to distort per-account spend, the narrower answer is to treat
   `salesTaxReturn` like `payment`.
