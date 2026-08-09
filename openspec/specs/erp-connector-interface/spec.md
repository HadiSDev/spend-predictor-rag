# ERP Connector Interface Specification

## Purpose

Define the abstract interface that all ERP integrations must implement. Every ERP adapter (mock, e-conomic, Business Central, Visma.net, Dinero, IFS Cloud) conforms to this contract, so the pipeline and sync runner treat them identically.

## Interface

```python
class ErpConnector(ABC):
    """Contract for all ERP integrations."""

    @abstractmethod
    def authorize(self, config: dict) -> str:
        """Handshake with the ERP and return a token/session string.

        config contains connection details (API key, OAuth client/token, etc.).
        Raises ErpAuthError on failure.
        """

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify credentials and API reachability without fetching data."""

    @abstractmethod
    def fetch_accounts(self) -> list[ErpAccountData]:
        """Full chart of accounts from the ERP.

        Returns the ERP's native accounts (ErpAccountData), not the
        company's spend tree. The categorizer later maps these to
        the company's Account model.
        """

    @abstractmethod
    def fetch_vendors(self, since: date | None = None) -> list[ErpVendorData]:
        """Vendor master. Optional date filter for incremental sync."""

    @abstractmethod
    def fetch_invoices(
        self, since: date | None = None
    ) -> list[ErpInvoiceData]:
        """Purchase invoices with line items.

        Each ErpInvoiceData includes its lines. The sync runner splits
        them into Invoice + InvoiceLine records.
        """
```

## Data Transfer Objects

These are the normalized Pydantic models every connector returns. The sync runner maps them to the SQLAlchemy ORM models before persisting.

```python
class ErpAccountData(BaseModel):
    erp_account_code: str
    erp_account_name: str
    erp_account_type: str | None     # "asset" | "liability" | "equity" | "income" | "expense"
    parent_code: str | None
    is_active: bool
    raw: dict

class ErpVendorData(BaseModel):
    erp_id: str
    name: str
    country_code: str | None
    vat_number: str | None
    raw: dict

class ErpInvoiceLineData(BaseModel):
    line_erp_id: str | None
    description: str
    quantity: float | None
    unit_price: float | None
    amount: float
    native_account_code: str | None   # ERP's own account for this line
    raw: dict

class ErpInvoiceData(BaseModel):
    erp_id: str
    vendor_erp_id: str
    vendor_name: str
    invoice_number: str
    invoice_date: date
    currency: str
    total: float
    tax: float | None
    lines: list[ErpInvoiceLineData]
    raw: dict
```

## Error Handling

```python
class ErpConnectionError(Exception):
    """Network error, timeout, unreachable host."""

class ErpAuthError(Exception):
    """Invalid or expired credentials."""

class ErpRateLimitError(Exception):
    """Rate-limited by ERP. Retry after X seconds."""

class ErpDataError(Exception):
    """Malformed or unexpected data from ERP."""
```

## Implementations

| Connector | Authorize | Accounts | Vendors | Invoices |
|---|---|---|---|---|
| **MockErpConnector** | API key → always succeeds | Hardcoded 25 accounts | Generated N vendors, includes redundant pairs | Generated M invoices over N months |
| **EconomicConnector** | API key + grant token | `GET /accounts` | `GET /suppliers` | `GET /invoices/booked` + lines |
| **BusinessCentralConnector** | OAuth 2.0 (Microsoft) | `GET /companies/{id}/accounts` | `GET /vendors` | `GET /purchaseInvoices` + lines |
| *(more to follow)* | | | | |

## Sync Runner Integration

The sync runner uses the connector interface polymorphically:

```python
def run_sync(company_id: str, erp_type: str, config: dict) -> SyncSummary:
    connector = get_connector(erp_type, config)
    connector.authorize(config)

    # 1. Accounts
    erp_accounts = connector.fetch_accounts()
    persist_erp_accounts(company_id, erp_integration_id, erp_accounts)

    # 2. Vendors
    vendors = connector.fetch_vendors(since=watermark)
    persist_vendors(company_id, vendors)

    # 3. Invoices
    invoices = connector.fetch_invoices(since=watermark)
    for inv in invoices:
        invoice = persist_invoice(company_id, erp_integration_id, inv)
        for line in inv.lines:
            persist_invoice_line(invoice.id, line)
            # ... later: categorizer picks up pending lines
```

## Project Structure

```
src/web_api/
├── connectors/
│   ├── __init__.py          ← get_connector() factory
│   ├── base.py              ← ErpConnector ABC, DTOs, error classes
│   ├── mock.py              ← MockErpConnector
│   └── ...
```

## Requirements

### Requirement: Connector fetches entries as the primary ledger unit

The `ErpConnector` interface SHALL expose `fetch_entries(since: date | None) ->
list[ErpEntryData]` returning normalized GL postings. Entries are the atomic
financial records real ERPs expose; every implementation SHALL provide this
method.

`ErpEntryData` SHALL be a normalized DTO carrying at least:

- `erp_entry_id` (native entry id), `voucher_id` (the voucher this posting
  belongs to), `entry_type` (e.g. `purchase_invoice`, `journal_entry`,
  `payment`, `credit_note`)
- `erp_account_code` (native account), `entry_date`, `description`
- `debit_amount`, `credit_amount`, `currency`
- `raw` (original ERP record)

`since` SHALL filter entries incrementally by posting date when supplied.

#### Scenario: fetch_entries returns voucher-tagged postings

- **WHEN** `fetch_entries()` is called against a connected ERP
- **THEN** it returns `ErpEntryData` records each carrying a `voucher_id` and its
  native account code, debit/credit amounts, and entry type

#### Scenario: Incremental entry fetch honors the watermark

- **WHEN** `fetch_entries(since=D)` is called
- **THEN** only entries with an entry date on or after `D` are returned

### Requirement: Invoice scans are retrieved per voucher

Invoice scans (line items plus the attached document reference) SHALL be
retrievable **per voucher** rather than only as a flat invoice list, because in
the real ERP the scan is a separate resource keyed by the voucher that its
entries carry.

- The connector SHALL provide a way to obtain the invoice scan for a given
  voucher (e.g. `fetch_invoice_scan(voucher_id) -> ErpInvoiceData | None`),
  returning `None` when the voucher has no scan.
- `ErpInvoiceData` SHALL expose the `voucher_id` it corresponds to and, when
  present, a reference to the attached scan document (filename / storage key /
  content) sufficient for the runner to record a `File`.

#### Scenario: Scan fetched for an invoice-bearing voucher

- **WHEN** entries reference voucher V whose `entry_type` is `purchase_invoice`
- **THEN** the connector can return the `ErpInvoiceData` scan for V, including its
  lines and attached-document reference

#### Scenario: Voucher without a scan yields no invoice

- **WHEN** the invoice scan for a voucher is requested but the voucher has no
  scanned document (e.g. a payment voucher)
- **THEN** the connector returns `None` and no `Invoice` is created for it

### Requirement: Sync runner ingests entries before invoice scans

The sync-runner integration SHALL follow an entry-first ordering: fetch entries,
group them by voucher, fetch and persist the invoice scan (with lines and file)
for invoice-bearing vouchers, then persist entries linked to the matching
invoice via `source_invoice_id`.

#### Scenario: Runner links persisted entries to their invoice scan

- **WHEN** a sync run processes a voucher with a purchase-invoice scan and several
  entries
- **THEN** the invoice scan and its lines are persisted first, and each entry is
  persisted with `source_invoice_id` pointing at that invoice

### Requirement: fetch_entries filters by selected account codes

`fetch_entries` SHALL accept an optional set of account codes and, when provided, return only entries whose native account is in that set, so the sync pulls only the selected accounts instead of the whole ledger.

- The signature SHALL be `fetch_entries(since: date | None = None, account_codes:
  set[str] | None = None) -> list[ErpEntryData]`.
- When `account_codes` is `None`, the connector SHALL return entries for all
  accounts (unfiltered), preserving existing behavior.
- When `account_codes` is an empty set, the connector SHALL return no entries.
- Filtering by account SHALL compose with the existing `since` date filter.

#### Scenario: Only selected accounts are returned

- **WHEN** `fetch_entries(account_codes={"6010"})` is called
- **THEN** every returned entry has `erp_account_code == "6010"`

#### Scenario: Empty selection returns nothing

- **WHEN** `fetch_entries(account_codes=set())` is called
- **THEN** no entries are returned

### Requirement: ErpAccountData carries the VAT characteristic

`ErpAccountData` SHALL expose a `with_vat` boolean so the runner can persist whether each ERP account is configured with or without VAT.

- The connector SHALL populate `with_vat` from the ERP account payload.
- `with_vat` SHALL default to a safe value (e.g. `false`) when the ERP omits it.

#### Scenario: Connector maps the VAT flag from the ERP payload

- **WHEN** the ERP account payload marks an account as with-VAT
- **THEN** the mapped `ErpAccountData` has `with_vat = true`

### Requirement: HTTP connectors share one base with a per-request auth hook

Connectors that talk to an ERP over HTTP SHALL derive from a shared
`HttpErpConnector` base that owns the HTTP client, header assembly, status-code
to exception mapping, retry, and binary fetch, so this logic exists once rather
than once per ERP.

- A subclass SHALL supply its authentication by implementing a hook returning
  the headers to send.
- That hook SHALL be evaluated **on every request**, not once at `authorize()`,
  so a connector whose token expires can refresh it without any change to the
  `ErpConnector` interface or to any caller.
- The base SHALL expose the HTTP client as an injectable attribute so tests can
  substitute a transport without patching internals or reaching the network.
- The abstract method signatures of `ErpConnector` SHALL be unchanged by this
  base.

#### Scenario: Auth headers are re-evaluated per request

- **WHEN** a connector performs two requests and its auth hook returns a
  different token the second time
- **THEN** the second request carries the second token

#### Scenario: Tests substitute the transport

- **WHEN** a test assigns a stub HTTP client to the connector before calling a
  fetch method
- **THEN** the connector uses it and issues no outbound network request

### Requirement: HTTP status codes map to the declared connector errors

The shared base SHALL translate ERP responses into the connector error
vocabulary consistently for every connector.

- HTTP 401 or 403 SHALL raise `ErpAuthError`.
- HTTP 429 SHALL raise `ErpRateLimitError`, carrying the retry delay when the
  ERP supplies one. It SHALL NOT be reported as `ErpDataError`: a caller must be
  able to tell "back off and retry" from "the ERP sent nonsense".
- HTTP 5xx and transport failures SHALL raise `ErpConnectionError`.
- Any other unexpected status SHALL raise `ErpDataError`.
- Before raising, the base SHALL retry a rate-limited or server-error response a
  bounded number of times with backoff. Once the bound is exhausted the error
  SHALL escape, and the sync runner's existing per-integration isolation records
  it against that integration alone.

#### Scenario: A rate-limited ERP raises the rate-limit error

- **WHEN** the ERP answers HTTP 429 on every attempt
- **THEN** `ErpRateLimitError` is raised after the bounded retries, not
  `ErpDataError`

#### Scenario: A transient server error is retried

- **WHEN** the ERP answers HTTP 503 once and then succeeds
- **THEN** the call returns the successful response and raises nothing

#### Scenario: An unreachable host is a connection error

- **WHEN** the HTTP request fails at the transport layer
- **THEN** `ErpConnectionError` is raised

### Requirement: Pagination is a declared strategy, not per-connector code

The connector layer SHALL provide pagination strategies that a connector selects
by declaration, so paging style is configuration rather than duplicated loops.

- The layer SHALL provide at least: page-number paging (a page index and size,
  stopping on a reported total), skip-pages paging (stopping on a
  next-page indicator), and cursor paging (following a next-link until absent).
- A connector SHALL declare which strategy it uses, and the shared base SHALL
  drive it and return the accumulated items.
- Switching a connector between strategies SHALL require no change to its field
  mapping code.

#### Scenario: A paged listing accumulates every item

- **WHEN** a connector using page-number paging lists a resource whose results
  span three pages
- **THEN** every item from all three pages is returned in one list

#### Scenario: Cursor paging stops when the link is absent

- **WHEN** a connector using cursor paging receives a page carrying no next-link
- **THEN** paging stops and no further request is made

### Requirement: A connector may filter by account after fetching

A connector whose ERP cannot filter entries by account SHALL apply the
`account_codes` selection itself after fetching: the filter is defined by its
**result**, not by where the filtering happens.

- The observable behaviour SHALL be identical either way: `None` returns all
  accounts, an empty set returns no entries, and a non-empty set returns only
  entries whose account is in it.
- An empty set SHALL short-circuit before any request, regardless of strategy.
- A connector that filters client-side SHALL document that it fetches the full
  ledger for the date window, because that cost is invisible in the signature.

#### Scenario: Client-side filtering is observably identical

- **WHEN** `fetch_entries(account_codes={"1350"})` is called on a connector that
  filters client-side
- **THEN** every returned entry has `erp_account_code == "1350"`, exactly as for
  a connector that filters at the ERP

#### Scenario: An empty selection issues no request

- **WHEN** `fetch_entries(account_codes=set())` is called on any connector
- **THEN** no entries are returned and no HTTP request is issued

### Requirement: A connector may declare brand metadata for its catalog entry

`ErpConnector` SHALL support optional class-level brand metadata alongside
`display_label`, so a client can present a connector recognisably without
knowing any connector by name.

- The metadata SHALL comprise a brand key for locating artwork, a short
  human-readable description of the ERP, and a link to its documentation.
- All three SHALL be optional. A connector declaring none SHALL produce exactly
  the catalog entry it produces today.
- The metadata SHALL be declarative class attributes, so registering a connector
  remains the whole of the wiring needed for it to appear in a client.

#### Scenario: A connector declaring brand metadata exposes it

- **WHEN** a connector declares a brand key, description and documentation link
- **THEN** the connector catalog carries all three for that connector

#### Scenario: A connector declaring none is unaffected

- **WHEN** a connector declares no brand metadata
- **THEN** its catalog entry carries its `erp_type`, label and credential fields
  as before, with the brand fields absent
