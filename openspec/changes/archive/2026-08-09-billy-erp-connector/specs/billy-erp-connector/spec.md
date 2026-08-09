## ADDED Requirements

### Requirement: A `billy` connector is registered in the catalog

The connector registry SHALL contain a connector registered under the `erp_type`
key `billy`, implementing every abstract method of `ErpConnector` against Billy
API v2.

- It SHALL declare the display label `Billy`, so `GET /api/v1/erp-types` offers
  it and `POST /api/v1/companies` accepts `billy` as an `erp_type`.
- Registering it SHALL require no database migration and no change to the sync
  runner, the ORM, or the reporting layer.

#### Scenario: Billy appears in the connector catalog

- **WHEN** an authenticated caller GETs `/api/v1/erp-types`
- **THEN** the response contains an entry whose `erp_type` is `billy`, carrying
  its label and its credential field descriptors

#### Scenario: A company can be created against Billy

- **WHEN** a manager POSTs a company whose `integration` block has
  `erp_type: "billy"` and the required credentials
- **THEN** the company, its `ErpIntegration` and its encrypted credential are
  written in one transaction, exactly as for any other connector

### Requirement: Billy authenticates with a revocable access token

The connector SHALL authenticate using Billy's `X-Access-Token` header and SHALL
NOT offer Billy's email/password Basic authentication, because a password grants
unscoped, non-revocable account access.

- `credential_fields` SHALL declare `access_token` as **required** and
  **secret**, `organization_id` as optional, and `base_url` as optional with the
  default `https://api.billysbilling.com/v2`.
- Every request the connector makes SHALL carry the `X-Access-Token` header.
- `authorize()` SHALL resolve the organization the token belongs to by calling
  Billy's organization endpoint and SHALL cache the resolved id for the life of
  the connector; a supplied `organization_id` SHALL override the discovered one.
- List requests that accept an organization filter SHALL carry the resolved
  organization id.
- `test_connection()` SHALL return `true` when the organization endpoint answers
  successfully, and SHALL return `false` when the ERP is unreachable.
- An invalid or revoked token SHALL raise `ErpAuthError`, distinct from an
  unreachable host.

#### Scenario: Creating an integration without a token is rejected

- **WHEN** a manager creates a `billy` integration with no `access_token`
- **THEN** the request is rejected, because the connector declares the field
  required

#### Scenario: A password field is rejected

- **WHEN** a manager creates a `billy` integration supplying a `password`
  credential
- **THEN** the request is rejected, because the key is not among the connector's
  declared `credential_fields`

#### Scenario: The organization is discovered from the token

- **WHEN** `authorize()` is called with no `organization_id` credential
- **THEN** the connector fetches the organization the token is bound to and uses
  its id for subsequent list requests, without the user having supplied it

#### Scenario: A revoked token is reported as an auth failure

- **WHEN** Billy answers a request with HTTP 401
- **THEN** the connector raises `ErpAuthError`, not `ErpConnectionError`

### Requirement: Billy accounts map onto `ErpAccountData`

`fetch_accounts()` SHALL return one `ErpAccountData` per Billy account.

- `erp_account_code` SHALL be the account's `accountNo` rendered as a string,
  and `erp_account_name` its `name`.
- `erp_account_type` SHALL be taken from the account's `natureId`, which is
  itself the semantic string (`expense`, `asset`, `liability`, `revenue`,
  `equity`) and so requires no second request and no sideload.
- `is_active` SHALL be the negation of the account's `isArchived` flag.
- `with_vat` SHALL be `true` when the Billy account has a default tax rate and
  `false` otherwise, seeding the customer setting exactly once.
- `parent_code` SHALL be `null`, because Billy account groups are not themselves
  accounts and asserting a parent that does not exist would break the chart.
- The full Billy payload SHALL be preserved in `raw`.

#### Scenario: An archived Billy account is marked inactive

- **WHEN** Billy returns an account with `isArchived: true`
- **THEN** the mapped `ErpAccountData` has `is_active = false`

#### Scenario: An account with a tax rate seeds the VAT characteristic

- **WHEN** Billy returns an account carrying a default tax rate
- **THEN** the mapped `ErpAccountData` has `with_vat = true`

#### Scenario: Account groups do not become parents

- **WHEN** Billy returns an account belonging to an account group
- **THEN** the mapped `ErpAccountData` has `parent_code = null`

### Requirement: Billy supplier contacts map onto `ErpVendorData`

`fetch_vendors()` SHALL return one `ErpVendorData` per Billy contact flagged as
a supplier, and SHALL NOT return contacts that are customers only.

- `erp_id` SHALL be the contact's id, `name` its `name`.
- `vat_number` SHALL be the contact's `registrationNo` (the CVR number in
  Denmark), which is what the sync runner's identity rule keys on.
- `country_code` SHALL be the contact's country reference.

#### Scenario: Customer-only contacts are excluded

- **WHEN** Billy's contact list contains a contact that is a customer and not a
  supplier
- **THEN** it does not appear in `fetch_vendors()` output

#### Scenario: The CVR number becomes the vendor VAT number

- **WHEN** a Billy supplier contact carries a `registrationNo`
- **THEN** the mapped `ErpVendorData` has that value as `vat_number`, so the
  runner deduplicates the supplier on it rather than on its name

### Requirement: Billy postings become entries grouped by their transaction

`fetch_entries()` SHALL return one `ErpEntryData` per Billy posting, sourced by
listing transactions with their postings embedded rather than by listing
postings individually.

- `voucher_id` SHALL be the **transaction's id**, not its `voucherNo`.
  `voucherNo` is per-daybook and per-fiscal-year and therefore repeats, while
  `voucher_id` is the key the sync runner joins entries to invoices on.
- `voucherNo` SHALL be preserved in `raw` so a client can display it.
- `erp_entry_id` SHALL be the posting's id.
- A posting names its account by `accountId`, so `erp_account_code` SHALL be the
  account **number** that id resolves to, using the chart the connector already
  fetches. A posting whose account cannot be resolved SHALL be dropped with a
  warning rather than stored under an empty code, which would pollute every
  per-account total.
- `accounting_date` SHALL be the posting's `entryDate`.
- A posting's `side` SHALL determine whether its amount lands in `debit_amount`
  or `credit_amount`; the other SHALL be `null`.
- `source_line_erp_id` SHALL be `null` on every Billy entry, because a Billy
  posting references its transaction and never a bill line. The connector SHALL
  NOT infer the link by matching account or amount.

#### Scenario: Postings of one transaction share a voucher

- **WHEN** Billy returns a transaction with three postings
- **THEN** three entries are returned, all carrying the same `voucher_id`, and
  that value is the transaction's id

#### Scenario: The display voucher number is not used as the join key

- **WHEN** two transactions in different fiscal years share the `voucherNo` `1`
- **THEN** their entries carry different `voucher_id` values, so they are not
  grouped together

#### Scenario: Entries carry no line reference

- **WHEN** any Billy entry is returned
- **THEN** its `source_line_erp_id` is `null`

#### Scenario: A credit posting fills only the credit amount

- **WHEN** Billy returns a posting whose `side` is credit
- **THEN** the mapped entry has `credit_amount` set and `debit_amount` null

#### Scenario: The posting's account id becomes an account number

- **WHEN** a posting names account id `X`, which the chart reports as account
  number `1350`
- **THEN** the mapped entry has `erp_account_code == "1350"`

#### Scenario: A posting on an unknown account is dropped

- **WHEN** a posting names an account id absent from the chart
- **THEN** no entry is returned for it and the drop is logged, rather than an
  entry being stored with an empty account code

### Requirement: Voided transactions are excluded, both halves

The connector SHALL return entries for neither half of a voided pair: Billy
voids a transaction by leaving the original in place with `isVoided` set and
adding a reversal with `isVoid` set.

- Excluding both SHALL leave every total unchanged, since the pair nets to zero,
  and matches Billy's own reports, which treat a voided transaction as
  cancelled.
- Excluding both is also what keeps a bill resolvable from exactly one voucher:
  a voided bill is re-posted, so counting voided transactions would present the
  same bill under two voucher ids and duplicate the invoice.

#### Scenario: Neither half of a void pair produces entries

- **WHEN** a transaction with `isVoided` set and its reversal with `isVoid` set
  are both returned by Billy
- **THEN** `fetch_entries()` returns no entries for either

#### Scenario: A bill is reachable from one voucher only

- **WHEN** a bill has been voided and re-posted, so several transactions
  reference it
- **THEN** only the live transaction yields entries, so the bill is the invoice
  scan of exactly one voucher

### Requirement: Entry type is derived from the transaction's originator

The connector SHALL derive `entry_type` from the originator of the transaction a
posting belongs to, because Billy postings carry no entry type of their own.

- The originator's kind SHALL be read from the **`originatorReference`** string,
  which has the form `"<kind>:<id>"`. It SHALL NOT be read from the
  `originatorType` field, which Billy leaves null.
- The same string's id half SHALL be what `fetch_invoice_scan` resolves a bill
  from, so one field drives both.

| Originator kind | `entry_type` |
| --- | --- |
| `bill` with no credited bill | `purchase_invoice` |
| `bill` that credits another bill | `credit_note` |
| `bankPayment` | `payment` |
| `salesTaxPayment` | `payment` |
| `daybookTransaction` | `journal_entry` |
| `salesTaxReturn` | `journal_entry` |
| `invoice` (a sales invoice) | not returned |
| unrecognised or absent | `journal_entry` |

- A transaction originating from a **sales invoice** SHALL be skipped entirely:
  this is a spend tool and revenue postings are not spend.
- An **unrecognised** originator SHALL fall back to `journal_entry` rather than
  raising, because the posting still moved money through a selected account and
  dropping it would understate spend. The connector SHALL log each unrecognised
  originator kind once per run so a gap is visible rather than silent.

#### Scenario: A supplier bill produces purchase-invoice entries

- **WHEN** a transaction originating from a bill is returned
- **THEN** its entries have `entry_type = "purchase_invoice"`

#### Scenario: A crediting bill produces credit-note entries

- **WHEN** a transaction originates from a bill that credits another bill
- **THEN** its entries have `entry_type = "credit_note"`, not
  `purchase_invoice`

#### Scenario: Sales invoices are not returned

- **WHEN** a transaction originating from a sales invoice is encountered
- **THEN** none of its postings are returned as entries

#### Scenario: A VAT settlement is a journal entry and a VAT payment is a payment

- **WHEN** transactions originating from `salesTaxReturn` and `salesTaxPayment`
  are returned
- **THEN** their entries are typed `journal_entry` and `payment` respectively

#### Scenario: An unknown originator is kept as a journal entry

- **WHEN** a transaction has an originator kind the connector does not recognise
- **THEN** its entries are returned with `entry_type = "journal_entry"` and the
  unrecognised kind is logged once

#### Scenario: The null originatorType field is not consulted

- **WHEN** a transaction carries `originatorReference: "bill:…"` and
  `originatorType: null`
- **THEN** its entries are typed `purchase_invoice`, not the unrecognised
  fallback

### Requirement: The watermark bounds the scan by ordering, not by a date filter

The connector SHALL bound `since` by ordering rather than by asking the ERP to
filter, because Billy's transaction listing accepts date filters and ignores
them.

- The connector SHALL request transactions ordered by entry date, newest first,
  and SHALL stop paging once it reaches entries older than `since`.
- It SHALL NOT rely on `minEntryDate`, `maxEntryDate` or any equivalent
  parameter on the transaction listing: those are accepted silently and change
  nothing, so trusting one would re-fetch the whole ledger on every sync while
  appearing to honour the watermark.
- With no `since`, the connector SHALL page to the end of the ledger, which is
  what a backfill requires.

#### Scenario: An incremental sync stops early

- **WHEN** `fetch_entries(since=D)` is called and the ledger holds transactions
  both newer and older than `D`
- **THEN** only entries dated on or after `D` are returned, and paging stops
  rather than walking the whole ledger

#### Scenario: A backfill reads everything

- **WHEN** `fetch_entries()` is called with no `since`
- **THEN** every non-voided transaction's postings are returned

### Requirement: Billy filters entries by account after fetching

The connector SHALL apply the `account_codes` selection to the flattened
postings itself, because Billy's transaction listing cannot be filtered by
account.

- The observable contract SHALL be identical to a server-side filter: `None`
  returns all accounts, an empty set returns no entries, and a non-empty set
  returns only entries whose account is in it.
- An empty set SHALL short-circuit before any HTTP request is made.
- The connector SHALL fetch every transaction in the requested date window
  regardless of how few accounts are selected. This cost SHALL be stated rather
  than hidden, because it is the difference between a cheap and an expensive
  incremental sync.

#### Scenario: Unselected accounts are dropped

- **WHEN** `fetch_entries(account_codes={"1350"})` is called and Billy returns a
  transaction with postings on accounts `1350` and `6900`
- **THEN** only the `1350` posting is returned

#### Scenario: An empty selection makes no request

- **WHEN** `fetch_entries(account_codes=set())` is called
- **THEN** no entries are returned and no HTTP request is issued

### Requirement: A Billy bill is the invoice scan of its voucher

`fetch_invoice_scan(voucher_id)` SHALL return the supplier bill behind the given
transaction as an `ErpInvoiceData`, or `null` when the transaction did not
originate from a bill.

- The connector SHALL resolve the transaction to its originating bill and fetch
  that bill with its lines.
- The returned `ErpInvoiceData.voucher_id` SHALL be the same transaction id it
  was asked for, so the runner's voucher-to-invoice map is consistent.
- `invoice_number` SHALL be the bill's supplier invoice number, falling back to
  the transaction's `voucherNo` and then to the bill's id, because the supplier
  invoice number is user-entered and often blank.
- `invoice_date` SHALL be the bill's `entryDate`; `total` its `grossAmount`;
  `tax` its tax amount; `currency` its `currencyId`.
- Bill lines arrive **sideloaded beside** the bill rather than nested inside it,
  keyed to it by the line's own bill reference. Each SHALL become an
  `ErpInvoiceLineData` whose `line_erp_id` is the bill line's id, `description`
  its description, `amount` its amount, and `native_account_code` the account
  **number** its `accountId` resolves to.
- Repeated lookups during one sync SHALL NOT re-fetch data the connector has
  already retrieved.

#### Scenario: A payment voucher has no scan

- **WHEN** `fetch_invoice_scan()` is called with the id of a transaction
  originating from a bank payment
- **THEN** `null` is returned, and this is not an error

#### Scenario: The scan reports the voucher it was asked for

- **WHEN** `fetch_invoice_scan(t)` returns an invoice
- **THEN** that invoice's `voucher_id` equals `t`, so the runner links its
  entries to it

#### Scenario: A blank supplier invoice number falls back

- **WHEN** the Billy bill has no supplier invoice number
- **THEN** the mapped `invoice_number` is the transaction's `voucherNo`, and the
  bill id only if that is absent too

#### Scenario: Bill lines become invoice lines

- **WHEN** a Billy bill has two bill lines on different accounts
- **THEN** two `ErpInvoiceLineData` are returned, each carrying its own
  `line_erp_id` and `native_account_code`

### Requirement: Billy attachments are served as invoice documents

`fetch_invoice_document(voucher_id)` SHALL return the document attached to the
voucher's bill, or `null` when there is none.

- Attachments are a resource of their own, not a field of the bill: the
  connector SHALL find the attachment whose owner is the bill, read its file
  reference, and fetch that file record for its download location.
- The document's filename SHALL come from the file record, because the download
  response carries no content-disposition to read one from.
- When the file's download location is on a **different host** than the
  configured Billy base URL, the connector SHALL fetch it **without** the
  `X-Access-Token` header, so the credential is never sent to a third party.
  Billy stores documents on object storage that **accepts** the header rather
  than rejecting it, so no failure would ever reveal the credential being sent —
  which is why this is a rule and not a fallback.
- A voucher with no attachment SHALL return `null`. A fetch that **failed**
  SHALL raise `ErpConnectionError`, so a caller can tell "nothing is attached"
  from "we could not reach it".

#### Scenario: A bill with no attachment returns nothing

- **WHEN** the voucher's bill has no attachments
- **THEN** `null` is returned

#### Scenario: The credential is not sent to a foreign host

- **WHEN** the file's download location points at a host other than the Billy
  API base URL
- **THEN** the content is fetched with no `X-Access-Token` header

#### Scenario: An unreachable document is an error, not an absence

- **WHEN** fetching the document fails with a server error
- **THEN** `ErpConnectionError` is raised rather than `null` being returned

### Requirement: Billy behaviour is verified against fixtures, not the live API

The committed test suite SHALL exercise the connector against recorded Billy
responses injected through the connector's HTTP client, and SHALL make no
outbound request.

- Fixtures SHALL be captured from real Billy responses so they are shaped like
  the ERP rather than like our own DTOs.
- A live smoke check MAY exist for manual verification but SHALL be opt-in and
  SHALL NOT run as part of the default test command.

#### Scenario: The suite runs offline

- **WHEN** `uv run pytest` runs with no network access
- **THEN** every Billy connector test passes
