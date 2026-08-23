## Why

The voucher panel is where a human corrects what the ledger got wrong, and it is
the weakest surface in the product. Every field in it — a quantity, a unit price,
a total, an invoice date — is a bare text box. `Number(value)` converts what is
typed with no `NaN` guard, so a European `1,5` becomes `null` and the figure is
silently erased; a stored `Numeric(12,4)` comes back as `1234.50000` and is shown
verbatim. The invoice date is free text. The Lines tab stacks every line as a
full-width card, so a six-line invoice is a scroll rather than a review.

Two of the components this needs **already exist and are already exported** —
`NumberInput` (wrapping `react-number-format`) and `DatePicker` (wrapping
`react-day-picker`) — and neither is used anywhere but the kitchen-sink route.
The `frontend-ui-library` spec has required both since it was written. This
change is largely the delivery of a promise the spec already made.

Separately, an invoice line has exactly one free-text field end to end
(`LineItem.description` → `InvoiceLine.description`), and it is doing two jobs.
What was bought has a **name** — always present, short, comparable across
suppliers, and the thing a savings suggestion is actually about. A description is
prose that a supplier prints sometimes. Collapsing them means the product name is
only ever recoverable by reading a sentence, which is precisely the work this
product exists to remove.

## What Changes

**Invoice lines gain an item name**

- `InvoiceLine` gains a nullable `item_name`, stored beside `description`.
- **BREAKING (data)**: a migration moves every existing line's `description` into
  `item_name` and leaves `description` null. Item name becomes the always-present
  field, description the sometimes-present one. Any `verified_fields` entry
  naming `description` is rewritten to `item_name` in the same migration, so a
  human's settled field stays settled against the value it was settled on.
- The document extractor returns an item name and a description as separate
  fields; the ERP connectors map their single bill-line text to `item_name`.
- `item_name` joins `LINE_VALUE_AUDIT_FIELDS`, so a correction to it is
  recoverable — and joins `PATCH /invoice-lines/{id}`.

**The Lines tab reviews one line at a time**

- The stacked list is replaced by a single focused line card with Previous /
  Next, a position counter, and keyboard navigation. Exactly one line is rendered
  at a time.
- The card transition is directional — a Next slides in from the right, a
  Previous from the left — so the motion states which way the reviewer moved.
  Fully suppressed under `prefers-reduced-motion`.

**Numbers and dates stop being text boxes**

- Every numeric field in the line editor and the invoice header moves to
  `NumberInput`: thousands separators, a bounded decimal scale, and a parsed
  value that is never `NaN`.
- Money is displayed and submitted at 2 decimal places. `quantity` and
  `unit_price` keep the 4 the schema stores — clamping them to 2 would round a
  stored value on save.
- The invoice date moves to the existing `DatePicker`.
- **New** `CurrencyInput` component: a `NumberInput` bound to a currency code,
  rendering the right symbol and scale, exported from `components/ui/`.

**The invoice number shown is the one printed on the document**

- The editable "Invoice number" field binds to `document_invoice_number` — what
  the scan says — which becomes correctable through `PATCH /invoices/{id}` and
  joins `INVOICE_AUDIT_FIELDS`.
- The ERP's as-posted `invoice_number` moves to the panel's top-left metadata as
  read-only evidence. It stays uncorrectable: it is the ledger's own record.

## Capabilities

### New Capabilities

- `frontend-line-paging`: reviewing an invoice's lines one at a time — the paged
  card, its navigation, its keyboard model, its motion, and how it behaves at the
  first and last line, with no lines, and while an edit is unsaved.

### Modified Capabilities

- `domain-model`: `InvoiceLine` gains `item_name` as the primary statement of
  what was bought, with `description` demoted to supplementary prose; the
  document-number requirement gains that a human may correct it.
- `web-api-invoice-review`: line payloads carry `item_name`; `PATCH
  /invoice-lines/{id}` accepts it; `PATCH /invoices/{id}` accepts
  `document_invoice_number`.
- `audit-log`: `item_name` joins the line value-audit set and
  `document_invoice_number` joins the invoice set — required, not optional, since
  a correction is applied in place and the audit row is the only record of what
  was there before.
- `invoice-document-processing`: extraction returns an item name distinct from
  the description, and stores both.
- `sync-pipeline-orchestration`: the ERP line path and the stand-in path both
  write `item_name`; the stand-in path stops bypassing the verified-field guard.
- `frontend-erp-entries`: the Lines tab is paged rather than stacked; lines show
  an item name; the details tab uses real number and date controls and shows both
  invoice numbers in their correct roles.
- `frontend-ui-library`: `CurrencyInput` joins the required component set, and
  the already-required `NumberInput` / `DatePicker` become the mandated controls
  for money and dates rather than optional ones.

## Impact

**Database** — one migration chaining from `0005_invoice_corrections`: add
`invoice_lines.item_name` (nullable String), copy `description` into it, null
`description`, rewrite `verified_fields` entries. Downgrade reverses the copy.
Naming stays under 32 characters (`alembic_version.version_num` is `varchar(32)`).

**Backend** — `db/models/invoice_line.py`, `schemas.py`
(`InvoiceLineRead`/`InvoiceLineUpdate`/`InvoiceUpdate`), `audit.py` (two
tuples — which propagates automatically to `replace.py::_REMOVED_FIELDS` and
`runner.py::_WITHDRAWN_FIELDS`, both of which splat `LINE_VALUE_AUDIT_FIELDS`),
`routers/invoice_lines.py`, `routers/invoices.py`, `connectors/base.py`
(`ErpInvoiceLineData`), `connectors/billy.py`, `connectors/mock.py`.

**AI** — `ai_api/models.py::LineItem` gains `item_name`; the extraction prompts
must ask for the split; `documents/replace.py` and `sync/runner.py` persist it.

**Frontend** — `voucher-lines-tab.tsx` (rewritten around paging),
`line-editor.tsx`, `voucher-details-tab.tsx`, `voucher-table.tsx` (line rows show
the item name), `lib/types.ts`, and a new `ui/currency-input.tsx`.

**Dependencies** — none added. `react-number-format@5.4.5` and
`react-day-picker@10.0.1` are already declared. `date-fns` is present only as a
transitive dependency and MUST NOT be imported directly.

**Not affected** — reporting and aggregation read `amount`, never the text
fields. FX conversion is untouched. No endpoint is removed.
