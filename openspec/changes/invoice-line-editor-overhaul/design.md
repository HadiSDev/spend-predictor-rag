## Context

The voucher panel is the product's only correction surface. Two surveys of the
current code establish the starting position:

**The controls already exist.** `frontend/src/components/ui/number-input.tsx`
wraps `react-number-format`, `date-picker.tsx` composes `Popover` + `Calendar`
over `react-day-picker`, both are exported from the barrel, and both are declared
in `package.json` (`react-number-format@5.4.5`, `react-day-picker@10.0.1`). Their
only call site is the kitchen-sink route `src/routes/ui.tsx`. `line-editor.tsx`
and `voucher-details-tab.tsx` use bare `FieldControl` text boxes for every value,
including money and dates. There is no `type="number"`, no `type="date"`, no
`step`, and no `inputMode` anywhere in `frontend/src`.

**The parse is lossy in both editors.** `line-editor.tsx:80` and
`voucher-details-tab.tsx:166` share this shape:

```ts
changes[field] = current[field] === '' ? null : Number(current[field])
```

`Number('1,5')` is `NaN`, which serializes to JSON `null`, which the API accepts
as "clear this field". A reviewer typing a European decimal erases the figure and
is told nothing. On the read side, `String(line.amount)` renders a stored
`Numeric(12,4)` as `1234.50000`.

**One text field is doing two jobs.** `LineItem.description` (LLM) →
`InvoiceLine.description` → `InvoiceLineRead.description` is the entire chain.
There is no item name anywhere in `src/`.

There is no shadcn install here — no `components.json`, no `@radix-ui/*`. The kit
is hand-rolled on `@base-ui-components/react` and is shadcn-shaped by convention
only. shadcn's datepicker recipe is therefore a reference for *composition*, not
something to install.

## Goals / Non-Goals

**Goals:**

- One line at a time in the Lines tab, with navigation that cannot silently
  discard an edit.
- No editable numeric or date field left as free text, and no path by which
  unparseable input becomes a stored `null`.
- An item name distinct from a description, end to end — extractor, connectors,
  model, API, UI — with the existing text migrated into it.
- The number a reviewer sees and edits is the one printed on the document.
- A `CurrencyInput` that exists once and is used everywhere money is typed.

**Non-Goals:**

- Any change to reporting, aggregation, redundancy detection, or FX. They read
  `amount`; none reads the text fields.
- Removing `invoice_number` from the correctable set. It stops being *presented*
  as the editable field; the API surface is unchanged. Narrowing it would be an
  unrequested breaking change.
- Persisting `vat_code` / `vat_rate`, which the extractor already returns and
  `replace.py` already discards. Real, adjacent, and out of scope.
- Bulk editing across lines. Paging is a review flow, not a spreadsheet.
- Adding any dependency.

## Decisions

### D1 — The epic-design skill was consulted and mostly declined

The skill was invoked as asked. Its core apparatus — GSAP via CDN, six parallax
depth layers, floating idle loops, particle foregrounds, scroll-scrubbed pinned
sections — is built for cinematic marketing pages and is wrong here. This is a
drawer full of financial inputs; an invoice line that drifts on a float loop is
harder to read, and a CDN `<script>` has no place in a bundled Vite app that
declares its dependencies.

What was taken from it, and is specified: **directional reveals** (the entering
card travels from the edge that encodes the direction of travel, so motion
carries information rather than decoration), **GPU-safe properties only**
(`transform` / `opacity` / `clip-path`, never `width` / `top`), and **mandatory
`prefers-reduced-motion` suppression**. Its asset-inspection workflow is not
applicable — this change introduces no images.

*Alternative considered:* applying the skill wholesale. Rejected — it would have
produced a review surface that is slower to use, and the skill's own guidance
names `senior-frontend` as the right tool for application UI.

### D2 — Strictly one line rendered, not a rail or a disclosure

Confirmed with the user. Only the current line is in the DOM.

The reason to be strict about *rendered* rather than merely *visible*: hidden
siblings keep their inputs focusable and their local `useState` alive, so Tab
walks into an invisible line's amount field and a "dirty" check has to reason
about edits the reviewer cannot see. Unmounting makes the dirty state
unambiguous — there is exactly one card, and it either has pending edits or does
not.

*Alternatives considered:* a rail of all lines with one expanded (keeps the whole
invoice scannable, and lets a reviewer jump to line 7 directly — genuinely
better for review, but not what was chosen); a collapsible full list beside the
card. Both remain easy to add later, since the paged card is the same component
either way.

*Consequence, accepted:* a reviewer cannot compare two lines or scan the invoice
without stepping. The reconciliation notice stays on the tab, above the card, so
the whole-invoice signal is still present.

### D3 — Line identity in the URL, or component state?

The panel's tab is already URL state (`?tab=lines`), and the table already opens
the panel *on a specific line*. The paged card must open on that line, not on the
first — which means the current line has to be addressable.

**Decision: component state, seeded from the activated line, not a new search
param.** The URL already carries `voucher` / `entry` / `tab`; adding `line` means
every navigation writes history, and paging through a ten-line invoice would put
ten entries in the back stack. Back should leave the panel, not walk backwards
through lines.

The seed comes from the line the table activated. `VoucherTable` already sends
`tab: 'lines'`; it will also send the line id, which the panel uses as the
initial index and then owns.

*Alternative considered:* `?line=<id>`. Rejected on the history-pollution
grounds above. If line-level deep links are wanted later, `replace: true`
navigation gets them without the back-stack cost.

### D4 — Dirty-guard on paging, not autosave

Paging away from unsaved edits prompts. Autosaving on page would write
half-finished figures, and a save is already an explicit action in this editor
(`Save line`).

The prompt fires only when the card is dirty, which the editor already tracks
(`valuesDirty` gates the Save button). The pattern mirrors the panel's existing
`hasUnsavedChanges` / `onHeaderDirtyChange` wiring in `entries-panel.tsx`, so
this is an extension of a mechanism the panel already has rather than a new one.

### D5 — Decimal scale: money 2, quantity and unit price 4

The request was "round float inputs up to 2 decimals". Applied literally to every
field, this silently rounds stored data: `quantity` and `unit_price` are
`Numeric(12,4)`, and a control clamped to 2 would turn a stored `0.2500` into
`0.25` and a stored `0.1250` into `0.13` on the next save — a data change nobody
asked for, caused by opening a line and pressing Save.

So: **money fields** (`amount`, `total`, `tax` — all `Numeric(14,2)`) get
`decimalScale={2} fixedDecimalScale`. **`quantity` and `unit_price`** accept up to
4 and display trailing zeros trimmed, which fixes the actual complaint —
`1234.50000` on screen — without touching precision the schema deliberately
holds.

*Assumption stated:* the complaint was about display, not about wanting stored
precision reduced. If reducing `unit_price` to 2 decimals is genuinely wanted,
that is a schema change (`Numeric(12,4)` → `Numeric(12,2)`) plus a migration, and
should be its own change.

### D6 — `CurrencyInput` wraps `NumberInput`, and emits numbers

A thin wrapper: currency code in, symbol/scale out, unformatted numeric value on
change. `react-number-format`'s `onValueChange` already hands back
`{ value, floatValue, formattedValue }`; the component surfaces `floatValue ??
null` so a caller never re-parses a string it just formatted, and `NaN` is
structurally unreachable.

Currency symbol resolution uses `Intl.NumberFormat`, which is already how
`lib/format.ts::formatMoney` renders money. Reusing it keeps a field and its
read-only echo from disagreeing about how DKK is written.

### D7 — Migrate `description` → `item_name`, and carry `verified_fields` with it

Confirmed with the user: the migration moves the value rather than leaving the
backlog with null names.

The non-obvious half is `verified_fields`. A line whose `verified_fields`
contains `"description"` has a human's assertion attached to a value that is
about to live in a different column. Leaving it would mean the sync's guard
protects an now-empty `description` while freely overwriting the `item_name` that
holds the human's actual work — the guarantee inverted by a migration. So the
same statement rewrites `"description"` → `"item_name"` in that JSON array.

The user chose the plain migration over the audit-every-row variant. Recorded
here because it is a real trade: the move is not recoverable from the audit log,
only from a database backup. It is defensible — the value is not lost, it is in
the adjacent column, and the migration is mechanical and reversible.

*Downgrade:* copies `item_name` back into `description`, drops the column, and
reverses the `verified_fields` rewrite.

### D8 — The connectors write `item_name`, and leave `description` null

An ERP bill line and a ledger posting each carry exactly one free-text field.
Writing it to both columns would make the distinction meaningless on the day it
was introduced; writing it to `description` only would leave the
always-present field empty on most of the ledger. It goes to `item_name`.

### D9 — Fix the stand-in path's missing verified-field guard

`runner.py:836` writes `lrow.description = entry.description` directly, while the
ERP-line path at L500 goes through `_assigner()`, which respects
`verified_fields`. A human's correction to a stand-in line is therefore marked
verified by the API and then overwritten by the next sync.

This is a pre-existing bug, not one this change introduces — but adding
`item_name` to that path without fixing it would extend a known defect to a new
field, so it is in scope.

## Risks / Trade-offs

**The `description` → `item_name` migration is not audited** → Recoverable only
from a backup. Mitigated by a reversible downgrade and by running the migration
test suite (`tests/web_api/test_migrations.py`, which runs the chain from base
against a throwaway PostgreSQL) before deploying. Take a backup first.

**Paging hides the rest of the invoice** → A reviewer can no longer see that
line 5 duplicates line 2. Mitigated by keeping the reconciliation notice and the
position counter above the card; the rail variant (D2) remains available if this
proves painful in use.

**`decimalScale` on an existing value can round on save** → Mitigated by D5:
money is 2 because it is stored at 2; quantity and unit price stay at 4. The spec
carries a scenario pinning that opening and saving an unedited `0.2500` does not
change it.

**Prompting on every page-away could be worse than the problem** → Mitigated by
firing only when genuinely dirty. If the editor's `valuesDirty` is over-eager
(e.g. reports dirty after a formatter normalizes `1234.50000` to `1,234.50` on
mount), the prompt fires on every step. **This is the sharpest implementation
risk in the change** — the dirty check must compare parsed values, not the
strings in the inputs.

**`item_name` reaches the extractor prompt** → Asking a small local model to
split name from description may degrade extraction quality on documents it
currently reads. Mitigated by the fallback rule (one text ⇒ it is the name) and
by reconciliation, which is unaffected — the split is textual and touches no
amount. Worth re-running the document corpus and comparing the read count.

**Eight capability specs touched** → Wide blast radius for one change. Accepted:
the item-name field genuinely crosses every layer, and splitting it into a
backend change and a frontend change would leave a released state where the
column exists and nothing writes it.

## Migration Plan

1. Back up the database. The `description` → `item_name` move is reversible by
   the downgrade but not by the audit log.
2. `uv run alembic upgrade head` — adds the column, moves the values, rewrites
   `verified_fields`.
3. Deploy backend and frontend together. The frontend labels lines by
   `item_name`; against an un-migrated API every line would fall back to
   `description`, which still renders but shows the old field under a new name.
4. Rollback: `uv run alembic downgrade 0005_invoice_corrections` restores
   `description` and drops `item_name`.

No re-extraction is required. Existing documents keep the text they had, now in
the name column; a reprocess picks up the split.

## Open Questions

- Should `item_name` eventually become NOT NULL once the backlog is re-read? Not
  now — the stand-in path legitimately produces nameless lines.
- Should the paged card offer a "jump to line N" control? Deferred; the counter
  makes the need visible if it exists.
- `vat_code` / `vat_rate` are extracted and discarded. Worth persisting in a
  later change — noted, not scoped here.
