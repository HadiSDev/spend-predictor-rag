## ADDED Requirements

### Requirement: A voucher carries its invoice lines

`GET /api/v1/erp-entries/vouchers` and the voucher-detail endpoints SHALL carry
the voucher's **invoice lines** alongside its entries, resolved server-side from
the voucher's source invoice.

- Each line SHALL carry its description, quantity, unit price, amount, its
  base-currency conversion, its categorization result and status, and its
  `origin`. The client must be able to render the expanded voucher without a
  second request per row.
- The voucher SHALL also carry its invoice's `doc_status` and `doc_error`, so
  the reader can tell provisional lines from read-the-document lines and see why
  processing failed.
- A voucher with no source invoice — a journal entry, a transfer — SHALL carry
  an empty line list, not an error. Lines are not universal and their absence is
  ordinary.
- The lines SHALL be ordered deterministically, so a voucher reads the same on
  every request.
- Adding lines SHALL NOT change which vouchers are returned, how they are
  grouped, how they are paginated, or what their amount is. The grouping,
  filtering and `currency_mode` rules are unchanged, and the voucher's amount
  remains the net of its **expense postings** — never a sum of its lines, which
  may legitimately differ.

#### Scenario: A voucher arrives with its lines

- **WHEN** a caller lists voucher groups and a voucher's invoice has three lines
- **THEN** the group carries those three lines with their descriptions, amounts,
  conversions, categories, statuses and origins

#### Scenario: Processing state travels with the voucher

- **WHEN** a voucher's invoice is `failed`
- **THEN** the group carries `doc_status = failed` and the failure's reason

#### Scenario: A voucher with no invoice has no lines

- **WHEN** a journal-entry voucher with no source invoice is returned
- **THEN** its line list is empty and the response is `200 OK`

#### Scenario: Lines do not change the voucher's amount

- **WHEN** a voucher's extracted lines sum to a figure other than its net
  expense postings
- **THEN** the voucher's amount is still the net of its expense postings

#### Scenario: Grouping and pagination are unaffected

- **WHEN** the same request is made before and after lines are carried
- **THEN** the same vouchers are returned, in the same order, on the same pages

### Requirement: An entry's category is null once its line is no longer identifiable

`ErpEntryRead.spend_category_level_1/2/3` SHALL remain read through
`source_invoice_line_id`, and SHALL be null when document extraction has
replaced the invoice's lines and left the posting unlinked.

- The category SHALL NOT be recovered by matching a posting to an extracted line
  on amount, account or description. An extracted line has no ERP line identity,
  and a guessed link would attach a category to a posting on no evidence — the
  same reason the sync derives the link rather than matching it.
- This SHALL NOT reduce what the reader sees, because the category is now shown
  on the line, which is what the Entries page lists.

#### Scenario: A posting unlinked by extraction shows no category

- **WHEN** an invoice's ERP lines have been replaced by extracted ones and its
  postings are unlinked
- **THEN** each posting's category levels are null

#### Scenario: No category is guessed

- **WHEN** exactly one extracted line carries the same amount as an unlinked
  posting
- **THEN** the posting's category is still null
