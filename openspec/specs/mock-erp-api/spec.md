# Mock ERP API Specification

## Purpose

A FastAPI server that mimics a real ERP API (e-conomic-style REST) for development, testing, and demo. Returns paginated, realistic data for vendors, invoices, invoice lines, and accounts. Configurable to plant redundancies and price variations.

## Stack

- **FastAPI** (lightweight, auto-docs at `/docs`)
- **Faker** + existing synthetic data logic for realistic content
- **In-memory storage** (dicts seeded on startup, resettable)
- **No database** — restart resets data

## API Endpoints

Modeled after e-conomic REST API conventions (RESTful, paginated, JSON).

### Authentication

Simple API key header: `X-AppSecretToken: mock-secret`

### Pagination

All list endpoints return:

```json
{
  "collection": [...],
  "pagination": {
    "maxPageSize": 20,
    "page": 1,
    "results": 20,
    "total": 150
  }
}
```

Query params: `page` (1-based), `pageSize` (default 20, max 100)

### Vendors

```
GET /api/v1/vendors?page=1&pageSize=20
GET /api/v1/vendors/{id}

Response:
{
  "vendorNumber": 1,
  "name": "Acme Cloud Services Ltd",
  "country": "DK",
  "vatNumber": "DK12345678",
  "currency": "DKK",
  "supplierGroup": {
    "supplierGroupNumber": 1,
    "name": "IT Services"
  }
}
```

### Accounts (Chart of Accounts)

```
GET /api/v1/accounts?page=1&pageSize=100
GET /api/v1/accounts/{accountNumber}

Response:
{
  "accountNumber": 6010,
  "name": "Cloud Hosting & Infrastructure",
  "accountType": "expense",
  "isActive": true,
  "balance": 0
}
```

### Invoices (Purchase Invoices)

```
GET /api/v1/purchase-invoices?page=1&pageSize=20
GET /api/v1/purchase-invoices/{id}

Response:
{
  "purchaseInvoiceNumber": 1001,
  "supplier": {
    "supplierNumber": 1,
    "name": "Acme Cloud Services Ltd"
  },
  "date": "2026-01-15",
  "currency": "DKK",
  "grossAmount": 12000.00,
  "netAmount": 9600.00,
  "vatAmount": 2400.00,
  "lines": [...]
}
```

### Invoice Lines (included in invoice or standalone)

```
GET /api/v1/purchase-invoices/{id}/lines

Response:
[{
  "lineNumber": 1,
  "description": "Cloud server - monthly hosting (Jan 2026)",
  "quantity": 1,
  "unitPrice": 9600.00,
  "netAmount": 9600.00,
  "account": { "accountNumber": 6010, "name": "Cloud Hosting & Infrastructure" },
  "vatRate": 25.0
}]
```

### Health / Status

```
GET /api/v1/health

Response: { "status": "ok", "mode": "mock", "dataGenerated": "2026-06-28T12:00:00Z" }
```

### Admin (control the mock)

```
POST /api/v1/admin/reset
  Body: { "seed": 42, "n_vendors": 30, "n_invoices": 500, "n_months": 12 }
  → Regenerates all data with the given seed

GET /api/v1/admin/stats
  → Returns: { "vendors": 30, "accounts": 25, "invoices": 500, "lines": 2500 }
```

## Data Generation Strategy

On startup (or reset), generate data in-memory:

1. **Accounts**: 25 standard e-conomic-style accounts (mix of expense, income, asset, liability). Hardcoded but realistic.

2. **Vendors**: N vendors (default 30), each assigned to 1-2 supplier groups:
   - 15 expense vendors (cloud, software, office, consulting, etc.)
   - 10 service vendors (legal, accounting, marketing)
   - 5 "redundant" vendor pairs (see below)

3. **Invoices**: M invoices over N months (default 500 over 12 months):
   - Monthly recurring patterns (rent, subscriptions, retainer contracts)
   - Seasonal spikes (marketing in Q4, travel in summer)
   - Random one-off purchases

4. **Redundant vendors**: 5 planted pairs:
   - Pair A/B both sell cloud hosting, B is 10% cheaper
   - Pair C/D both sell office supplies, D is 15% cheaper
   - Pair E/F both sell marketing services
   - Pair G/H both sell consulting
   - Pair I/J both sell shipping/logistics

   Each pair shares a L2 category and has overlapping product descriptions.
   The ground truth savings is known: consolidating to the cheaper vendor
   yields (currently more expensive vendor's annual spend × price difference %).

## Integration with docker-compose

```yaml
mock-erp:
  build: ./mock_erp
  ports:
    - "8001:8000"
  environment:
    MOCK_ERP_SEED: "42"
    MOCK_ERP_VENDORS: "30"
    MOCK_ERP_INVOICES: "500"
    MOCK_ERP_MONTHS: "12"
```

## Project Structure

```
apps/mock-erp/src/mock_erp/
├── __init__.py
├── main.py              ← FastAPI app, startup, reset endpoint
├── models.py            ← Pydantic response models
├── data/
│   ├── accounts.py      ← Standard chart of accounts
│   ├── vendors.py       ← Vendor generation with redundant pairs
│   └── invoices.py      ← Invoice generation with temporal patterns
├── auth.py              ← API key validation
└── Dockerfile
```

## Use Cases

1. **Development**: Run the categorizer against mock API instead of synthetic DB — tests the full connector → pipeline → DB flow end-to-end
2. **Connector testing**: Test pagination, error handling, rate limiting, data mapping for each ErpConnector adapter
3. **Demo**: Start with `docker compose up`, point the dashboard at the mock ERP, and show the full product working with realistic data
4. **Benchmarking**: Known ground truth in mock data → measure categorization accuracy and redundancy detection precision/recall

## Open Questions

- [ ] Should the mock also simulate API errors (rate limiting, timeouts, 500s) to test error handling in connectors?
- [ ] Should we support "slow mode" (artificial latency per endpoint) to test dashboard responsiveness?

## Requirements

### Requirement: Entries endpoint exposes voucher-tagged postings

The mock ERP API SHALL expose `GET /api/v1/entries` returning paginated GL
postings that mirror the real entry-first shape, so the connector's
`fetch_entries` can be exercised end-to-end deterministically.

- Each entry item SHALL carry a native entry id, a `voucherId`, an `entryType`
  (`purchase_invoice` | `journal_entry` | `payment` | `credit_note`), a
  reference to its native account, `entryDate`, `description`, and debit/credit
  amounts with currency.
- The endpoint SHALL support the existing pagination contract
  (`?page=&pageSize=`, `collection` + `pagination`) and an optional `since` date
  filter.
- For every generated purchase invoice, the entries whose `voucherId` matches the
  invoice's voucher SHALL sum consistently with that invoice (net + VAT), so
  entry data and invoice data are mutually reconcilable.
- A purchase invoice SHALL produce **one expense posting per invoice line**,
  carrying that line's own `description` and `netAmount`, alongside the input-VAT
  debit and the accounts-payable credit. Lines SHALL NOT be netted per account.
  A posting's description is what makes a ledger row readable against the invoice
  it came from, and what ties it back to the `InvoiceLine` the categorizer
  worked on; netting threw that text away and — since every line of a generated
  invoice shares one account — collapsed each invoice to a single anonymous
  posting, so no voucher ever had more than one expense row.
- A line with no description SHALL still yield a human-readable posting, falling
  back to the vendor and account name.
- Each line-derived posting SHALL carry a `lineNumber` naming the invoice line it
  came from, and the VAT and payable postings SHALL carry `lineNumber` null —
  they belong to the whole invoice, so null is the correct answer rather than
  missing data. This is what an importer links a posting to its line by.

#### Scenario: List entries with pagination

- **WHEN** a client calls `GET /api/v1/entries?page=1&pageSize=100`
- **THEN** the response contains a `collection` of voucher-tagged entries and a
  `pagination` block, consistent with the other list endpoints

#### Scenario: Entries reconcile with their invoice

- **WHEN** a purchase invoice with voucher V is generated
- **THEN** `GET /api/v1/entries` includes entries tagged with `voucherId` V whose
  amounts reconcile with that invoice's net and VAT

#### Scenario: One posting per invoice line, carrying its text

- **WHEN** a purchase invoice with three lines is generated
- **THEN** its voucher has three expense postings whose descriptions and debit
  amounts equal those lines' descriptions and net amounts, plus the VAT and
  payable postings

#### Scenario: A multi-line invoice still balances

- **WHEN** the postings of a multi-line invoice's voucher are summed
- **THEN** total debit equals total credit equals the invoice's gross amount

#### Scenario: A posting names the line it came from

- **WHEN** a multi-line purchase invoice's postings are listed
- **THEN** each expense posting carries the `lineNumber` of its line, and the
  input-VAT and payable postings carry `lineNumber` null

### Requirement: Purchase invoices expose voucher id and attached file

Purchase-invoice payloads SHALL expose the `voucherId` they were posted under and
a reference to their attached scan document, so the connector can resolve the scan
per voucher and the runner can create the linked `File`. (The `voucherId` is used
to associate entries with the scan; it is stored on `ErpEntry`, not on the
`Invoice`.)

- Each purchase-invoice item SHALL include a `voucherId` matching the voucher of
  its corresponding entries.
- Each purchase-invoice item SHALL include an attached-file reference (e.g.
  filename and a storage key or download path) representing the scanned document.

#### Scenario: Invoice payload includes voucher and file reference

- **WHEN** a client fetches a purchase invoice from the mock ERP
- **THEN** the payload includes a `voucherId` and an attached-file reference for
  the scanned document

#### Scenario: Invoice voucher matches its entries

- **WHEN** a purchase invoice and its entries are generated for the same document
- **THEN** the invoice's `voucherId` equals the `voucherId` on those entries

### Requirement: Accounts expose a VAT flag

Account payloads from the mock ERP SHALL expose a `withVat` boolean so the connector can populate `ErpAccountData.with_vat`.

- Each account item SHALL include a `withVat` field.
- The generated chart SHALL include both with-VAT and without-VAT accounts so the
  flag is meaningfully exercised.

#### Scenario: Account payload includes the VAT flag

- **WHEN** a client fetches accounts from the mock ERP
- **THEN** each account item includes a boolean `withVat`

### Requirement: Entries endpoint filters by account codes

`GET /api/v1/entries` SHALL accept an optional `accounts` filter and, when present, return only entries whose account is in that set, mirroring the fetch-time account selection.

- The `accounts` parameter SHALL accept a comma-separated list of account codes.
- When `accounts` is omitted, all entries SHALL be returned (subject to
  pagination and any `since` filter).
- The `accounts` filter SHALL compose with the existing pagination and `since`
  contract.

#### Scenario: Entries are filtered to the requested accounts

- **WHEN** a client calls `GET /api/v1/entries?accounts=6010,6020`
- **THEN** every returned entry's account is `6010` or `6020`

#### Scenario: Omitting the filter returns all entries

- **WHEN** a client calls `GET /api/v1/entries` with no `accounts` parameter
- **THEN** entries for all accounts are returned, paginated as before
