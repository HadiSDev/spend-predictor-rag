# invoice-document-processing Specification

## Purpose

Turn an invoice's attached ERP document into `InvoiceLine` rows: a standalone
`ai_api` stage that discovers `pending` invoices from the database, fetches each
scan live through its own integration, extracts its lines, reconciles them
against the invoice total, and replaces the invoice's provisional lines — with
its own `doc_status` lifecycle, bounded attempts, and a management-gated
retrigger endpoint, kept deliberately out of the sync runner so a slow or
unavailable LLM never delays ledger data.

## Requirements

### Requirement: Document processing is a stage of its own, discovered from the database

An `ai_api` stage — `python -m ai_api.documents.runner` — SHALL turn an invoice's
attached document into `InvoiceLine` rows. Like the sync runner, it SHALL take no
tenant and no credentials as arguments: it discovers its work by querying for
invoices whose `doc_status` is `pending`, across every connected
`ErpIntegration`, and reaches the ERP through that integration's own decrypted
credentials.

- The stage SHALL NOT run inside the sync runner. The sync lands ledger data;
  this stage reads what the sync landed. A slow, rate-limited or unavailable LLM
  therefore delays no ledger data and advances no sync watermark.
- The stage SHALL claim an invoice by moving it to `processing` before doing any
  work, so two concurrent runs do not process the same invoice twice.
- The stage SHALL process invoices oldest-first by `invoice_date`, so a backlog
  drains in the order the spend was incurred.
- Failure SHALL be isolated per invoice: an extraction that raises records
  `failed` on that invoice and the run continues to the next one.
- `--company-id`, `--invoice-id` and `--limit` SHALL narrow the discovered set
  and SHALL NEVER create work that discovery did not find.

#### Scenario: The stage finds its own work

- **WHEN** the stage runs and three invoices across two companies are `pending`
- **THEN** all three are processed, each through its own company's integration
  credentials, with no tenant named on the command line

#### Scenario: The sync never waits on the document AI

- **WHEN** the LLM used for extraction is unreachable
- **THEN** `python -m ai_api.sync.runner` still completes, lands its entries and
  advances its watermark, and the affected invoices remain `pending`

#### Scenario: One bad document does not stop the run

- **WHEN** the second of five pending invoices raises during extraction
- **THEN** it is recorded `failed` with its error and the remaining three are
  still processed

#### Scenario: An invoice is claimed before work begins

- **WHEN** the stage picks up a pending invoice
- **THEN** that invoice reads `processing` before the document is fetched, and a
  concurrently running stage does not select it

#### Scenario: A selector narrows but never invents

- **WHEN** the stage is run with `--invoice-id` naming an invoice that is not
  `pending`
- **THEN** nothing is processed and the run reports that the selector matched no
  work

### Requirement: An invoice records its document-processing state

`Invoice` SHALL carry a `doc_status` of `not_applicable`, `pending`,
`processing`, `processed`, or `failed`, together with `doc_attempts`,
`doc_error` and `doc_processed_at`.

- An invoice with no attached document (`file_id IS NULL`) SHALL be
  `not_applicable`. This is not a failure: most vouchers have no scan, and the
  stand-in lines are the answer for them until a document appears.
- An invoice that gains a document on a later sync SHALL move from
  `not_applicable` to `pending`.
- `doc_attempts` SHALL increment on each processing attempt, and the stage SHALL
  NOT retry an invoice that has reached the configured attempt ceiling until it
  is explicitly retriggered.
- `doc_error` SHALL hold the reason for the most recent failure and SHALL be
  cleared when an attempt succeeds or the invoice is retriggered.
- `doc_status` SHALL be independent of `Invoice.status`. The latter is the
  categorization rollup of the invoice's lines and SHALL NOT be affected by
  document processing except through the lines it produces.

#### Scenario: A voucher with no scan is not a failure

- **WHEN** the sync lands an invoice with no attached document
- **THEN** its `doc_status` is `not_applicable`, `doc_error` is null, and it is
  never picked up by the stage

#### Scenario: A document arriving later queues the invoice

- **WHEN** a later sync attaches a document to an invoice that was
  `not_applicable`
- **THEN** its `doc_status` becomes `pending`

#### Scenario: Attempts are bounded

- **WHEN** an invoice has failed as many times as the configured ceiling
- **THEN** subsequent stage runs skip it, and it stays `failed` with its last
  error until retriggered

#### Scenario: Processing state does not disturb the categorization rollup

- **WHEN** an invoice's `doc_status` moves to `failed`
- **THEN** its `Invoice.status` still reflects only the categorization state of
  its lines

### Requirement: Extraction replaces the invoice's provisional lines

When extraction succeeds, the stage SHALL replace that invoice's lines whose
`origin` is `entry_fallback` or `erp` with the extracted lines, written with
`origin = 'document_ai'`, in one transaction.

- Replacement SHALL be whole-invoice. A partially replaced invoice would carry
  two descriptions of the same spend and double-count its total.
- Each removal SHALL append an `AuditLog` row naming what was removed and why,
  so a line that a human had verified is recoverable from the record rather than
  silently gone.
- The extracted lines SHALL be converted into the company's base currency at the
  invoice's own `invoice_date`, by the same rules as any other money-bearing row.
- Extracted lines SHALL be left `uncategorized`, so the next categorizer pass
  picks them up. The stage SHALL NOT categorize.
- `ErpEntry.source_invoice_line_id` on that invoice's postings SHALL be set to
  null where it pointed at a removed line, because an extracted line has no ERP
  line identity to match a posting against. Guessing a link would attach a
  category to a posting on no evidence.
- Re-running a successful extraction SHALL be idempotent in effect: the invoice
  ends with exactly the lines the latest extraction produced.

#### Scenario: Stand-in lines give way to extracted detail

- **WHEN** an invoice carrying two `entry_fallback` lines is processed and the
  document yields five lines
- **THEN** the invoice has exactly those five lines, each `origin='document_ai'`
  and `uncategorized`, and the two stand-ins are gone

#### Scenario: Removal is on the record

- **WHEN** a stand-in line that a human had verified is replaced
- **THEN** an audit row records the line, its verified values, and that an
  extraction superseded it

#### Scenario: Extracted lines land converted

- **WHEN** an invoice dated 2026-03-11 in EUR is extracted for a company whose
  base currency is DKK
- **THEN** each extracted line carries `base_currency`, `base_amount`, `fx_rate`
  and `fx_rate_date` resolved at 2026-03-11, not at today's rate

#### Scenario: Postings lose a link they can no longer support

- **WHEN** an invoice's postings referenced its ERP lines and those lines are
  replaced by extracted ones
- **THEN** those postings' `source_invoice_line_id` is null, and their spend
  category reads empty rather than showing another line's category

#### Scenario: A second extraction leaves one set of lines

- **WHEN** an already-`processed` invoice is retriggered and extracted again
- **THEN** it carries only the lines of the second extraction

### Requirement: An extraction that does not reconcile with the ledger is rejected

The stage SHALL compare the sum of the extracted lines against the invoice's own
`total`, and SHALL reject the extraction when it reconciles with neither the
gross nor the net-of-tax figure within the configured tolerance.

- A rejected extraction SHALL record `failed` with a reason naming both sums,
  and the invoice's existing lines SHALL stand. Lines that do not add up to the
  invoice are wrong, and wrong lines would be categorized, reported and acted on.
- Both the gross and the net comparison SHALL be tried, because a document may
  state its lines with or without VAT and the ERP's own `with_vat` flag describes
  the account, not the document.
- The tolerance SHALL be configurable and SHALL be relative as well as absolute,
  so a large invoice is not rejected over rounding and a small one is not
  accepted over a missed line.
- An invoice with no `total` SHALL skip the check rather than fail it — there is
  nothing to reconcile against.

#### Scenario: Lines that add up are accepted

- **WHEN** extraction of a 4.812,00 invoice yields lines summing to 4.812,00
- **THEN** the extraction is accepted

#### Scenario: A document stating lines net of VAT reconciles

- **WHEN** extraction of a 5.000,00 gross invoice carrying 1.000,00 tax yields
  lines summing to 4.000,00
- **THEN** the extraction is accepted against the net figure

#### Scenario: A missed line is rejected

- **WHEN** extraction of a 4.812,00 invoice yields lines summing to 3.200,00
- **THEN** the extraction is rejected, the invoice reads `failed` with both sums
  in its error, and its previous lines are unchanged

#### Scenario: Rounding does not reject

- **WHEN** extracted lines sum to 4.812,01 against a 4.812,00 invoice
- **THEN** the extraction is accepted

#### Scenario: Nothing to reconcile against

- **WHEN** the invoice has no `total`
- **THEN** the reconciliation check is skipped and the extraction is judged only
  on whether it produced lines

### Requirement: Processing can be retriggered from the API

The API SHALL provide `POST /api/v1/invoices/{id}/reprocess`, restricted to
management roles, which returns the invoice to `pending`, clears `doc_error`,
and resets the attempt count so the next stage run picks it up.

- It SHALL respond `409 Conflict` when the invoice has no attached document —
  there is nothing to process, and a pending invoice that can never succeed
  would sit in the queue forever.
- It SHALL respond `409 Conflict` when the invoice is currently `processing`, so
  a retrigger cannot race a run that is already working on it.
- It SHALL be permitted on a `processed` invoice, so a bad extraction can be
  redone once the extractor improves.
- It SHALL be tenant-scoped and SHALL respond `404 Not Found` for an invoice
  outside the caller's organization.
- The retrigger SHALL be audited with the acting user.

#### Scenario: A failed invoice is queued again

- **WHEN** a manager posts to `/invoices/{id}/reprocess` on a `failed` invoice
- **THEN** it reads `pending` with a null `doc_error` and a reset attempt count

#### Scenario: Nothing to reprocess

- **WHEN** the invoice has no attached document
- **THEN** the API responds `409 Conflict` and the invoice's state is unchanged

#### Scenario: A run in flight is not disturbed

- **WHEN** the invoice is `processing`
- **THEN** the API responds `409 Conflict`

#### Scenario: A good invoice may still be redone

- **WHEN** a manager reprocesses a `processed` invoice
- **THEN** it returns to `pending`

#### Scenario: A read-only member cannot retrigger

- **WHEN** a `viewer` posts to the endpoint
- **THEN** the API responds `403 Forbidden`

### Requirement: Extraction reads the document from the ERP, never a local copy

The stage SHALL fetch each document through the invoice's own integration at
processing time, by the same connector path `GET /invoices/{id}/document` uses.

- No document bytes SHALL be persisted. There is one copy of the scan, in the
  ERP, and a second one would be a copy to keep in sync.
- The extractor SHALL dispatch on the payload's declared media type, and SHALL
  record a clear failure for a media type it cannot read rather than feeding
  arbitrary bytes to a PDF parser.
- A document the ERP no longer serves SHALL record `failed` with that reason,
  and SHALL NOT remove the invoice's existing lines.

#### Scenario: The scan is fetched live

- **WHEN** an invoice is processed
- **THEN** the document is fetched from the ERP for that run and no copy of it
  is written to local storage

#### Scenario: A photographed receipt is not handed to a PDF parser

- **WHEN** the attached document is a JPEG
- **THEN** it is routed to an extractor that can read an image, or recorded as a
  clear unsupported-media failure — never parsed as a PDF

#### Scenario: A document the ERP has dropped

- **WHEN** the ERP returns 404 for the attachment
- **THEN** the invoice reads `failed` with that reason and keeps the lines it had

### Requirement: Extraction reads an item name distinct from the description

The document extractor SHALL return, per line, an item name and a description as
separate fields, and SHALL persist both.

- The item name is what was bought: the product or service as the document names
  it, without quantities, prices, dates or terms folded in.
- The description is any further prose the line printed. When the document states
  only one text, that text SHALL be the **item name** and the description SHALL
  be null — the name is the field every line is expected to carry.
- The model SHALL NOT invent a name. A line whose text cannot be read yields a
  null item name, on the same rule that an unreadable amount yields no amount
  rather than a guess.
- Neither field SHALL be required on a per-page reading. A page is a fragment,
  and a whole-invoice requirement applied to one page throws away a correct
  partial reading.

#### Scenario: A document stating both yields both

- **WHEN** a line reads "Figma Organization seat — annual plan, billed yearly"
  and the extractor separates them
- **THEN** the stored line has that item name and that description

#### Scenario: A document stating one text names the item

- **WHEN** a line's only text is "Cloudflare Pro subscription"
- **THEN** the stored line's `item_name` is that text and its `description` is
  null

#### Scenario: An unreadable line names nothing

- **WHEN** a line's text cannot be read from the page
- **THEN** `item_name` is null rather than a fabricated or partial value

#### Scenario: Replacement audits the item name it removed

- **WHEN** an extraction replaces existing lines
- **THEN** each removed line's `superseded_by_extraction` audit row carries its
  item name

### Requirement: Extraction stores the number it read as the document's number

The invoice number an extraction reads SHALL be stored as
`document_invoice_number` and SHALL NOT be written to `invoice_number`.

This restates an existing constraint because the field is becoming correctable:
once a human can edit it, the guarantee that extraction writes only the document
column is what keeps a later re-read from overwriting the ledger's own value.

A re-extraction SHALL respect the invoice's `verified_fields`: a
`document_invoice_number` a human has settled SHALL NOT be overwritten by a
subsequent extraction.

#### Scenario: A re-read does not overwrite a settled number

- **WHEN** an invoice whose `document_invoice_number` a human corrected is
  reprocessed and the model reads the original misprint again
- **THEN** the human's value stands

#### Scenario: A re-read fills an unsettled number

- **WHEN** an invoice whose `document_invoice_number` no human has touched is
  reprocessed
- **THEN** the newly read number replaces the previous one
