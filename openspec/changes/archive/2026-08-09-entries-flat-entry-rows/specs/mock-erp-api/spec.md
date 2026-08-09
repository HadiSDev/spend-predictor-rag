## MODIFIED Requirements

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
