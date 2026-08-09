## ADDED Requirements

### Requirement: The runner stands in a line for every expense posting with no better source

The runner SHALL write one `InvoiceLine` with `origin = 'entry_fallback'` per **expense** posting on a voucher whose invoice has no lines from a better source — that is, when no document extraction has succeeded and the ERP supplied no lines of its own.

- Only expense postings SHALL become lines. Input VAT, the payable, bank and
  other non-expense postings are not spend, and a line for each of them would
  make the invoice's lines sum to zero.
- The stand-in line SHALL take its description, amount, account code and
  currency from the posting, and SHALL be converted into the company's base
  currency at the invoice's `invoice_date` like any other line.
- The runner SHALL set `ErpEntry.source_invoice_line_id` on the posting the line
  stands in for, so the existing entry→line link continues to resolve and the
  posting shows its own category.
- The runner SHALL NOT overwrite lines of `origin = 'document_ai'`. Once the
  document has been read, a later sync must not reduce the invoice back to its
  postings.
- Stand-in lines SHALL be upserted deterministically from the posting they stand
  for, so a re-sync of the same voucher does not duplicate them.
- A voucher whose postings are all non-expense SHALL produce no lines rather
  than an empty placeholder line.

#### Scenario: A scanless voucher still yields lines

- **WHEN** a voucher of one expense posting, one input-VAT posting and one
  payable is synced, and the ERP supplied no bill lines
- **THEN** exactly one `entry_fallback` line is written, for the expense posting

#### Scenario: A split-account voucher yields a line per expense posting

- **WHEN** a voucher posts to two different expense accounts
- **THEN** two stand-in lines are written, one per posting, each carrying that
  posting's account code and amount

#### Scenario: The posting links to the line it produced

- **WHEN** a stand-in line is written for a posting
- **THEN** that posting's `source_invoice_line_id` names it

#### Scenario: Extracted lines survive a re-sync

- **WHEN** an invoice already carries `document_ai` lines and the voucher is
  synced again
- **THEN** those lines are untouched and no stand-in lines are added

#### Scenario: Re-syncing does not duplicate stand-ins

- **WHEN** the same voucher is synced twice
- **THEN** the invoice still carries exactly one stand-in line per expense
  posting

#### Scenario: A voucher with no expense posting yields no line

- **WHEN** a voucher carries only a transfer between balance accounts
- **THEN** no stand-in line is written for it

### Requirement: The runner queues documents but never processes them

The runner SHALL set `Invoice.doc_status` when it persists an invoice, and SHALL
NOT call the document AI.

- An invoice the runner writes with an attached document SHALL be `pending`.
- An invoice with no attached document SHALL be `not_applicable`.
- An invoice already `processed` SHALL keep that status unless the sync attaches
  a different document to it, in which case it SHALL return to `pending`.
- An invoice currently `processing` SHALL NOT have its status changed by a sync.
- An invoice that is `failed` SHALL stay `failed`. A sync is not a retry: the
  explicit path back is `POST /invoices/{id}/reprocess`, and requeueing on every
  sync would both make that endpoint pointless and re-run a document that has
  already proved it cannot be read. A *different* document is new evidence and
  returns the invoice to `pending` by the rule above.
- The runner's per-integration report SHALL state how many invoices it queued,
  so an operator can see the backlog the stage will face without querying the
  database.

#### Scenario: A scan queues its invoice

- **WHEN** the runner persists an invoice with an attached document
- **THEN** its `doc_status` is `pending` and no extraction is attempted during
  the sync

#### Scenario: A re-sync does not requeue a processed invoice

- **WHEN** an invoice that is `processed` is synced again with the same document
- **THEN** it stays `processed`

#### Scenario: A replaced scan requeues the invoice

- **WHEN** a sync attaches a different document to a `processed` invoice
- **THEN** it returns to `pending`

#### Scenario: A sync is not a retry

- **WHEN** an invoice that is `failed` is synced again with the same document
- **THEN** it stays `failed`, and only `POST /invoices/{id}/reprocess` returns it
  to `pending`

#### Scenario: A sync does not interrupt a run in flight

- **WHEN** an invoice is `processing` while a sync runs
- **THEN** its `doc_status` is left as it is

#### Scenario: The queue depth is reported

- **WHEN** a sync run completes
- **THEN** its per-integration report includes the number of invoices queued for
  document processing
