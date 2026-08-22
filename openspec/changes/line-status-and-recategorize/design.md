## Context

`InvoiceLine.status` is already persisted, already on `InvoiceLineRead`, and already
filterable (`GET /invoice-lines?status=`). Nothing about it reaches the Entries page: the
line table renders description, quantity, unit, unit price, spend category and amount, and
the categorization outcome is legible only as the *absence* of a category — which
`uncategorized`, `ai_failed`, and "this company has no spend tree" all produce identically.

The requeue half is constrained by the package boundary. `ai_api` imports the domain from
`web_api`; `web_api` never imports `ai_api`. The categorizer lives in
`ai_api/sync/categorizer.py` and runs only from `ai_api/sync/runner.py`, so no HTTP request
handler can execute it. `_categorize_pending` selects `status == UNCATEGORIZED`, which is
both why `ai_failed` is currently a dead end and why moving a line back to `uncategorized`
is sufficient to requeue it — no flag, no queue table, no new mechanism.

Two precedents shape the design: `POST /companies/{id}/recompute-fx` for a company-scoped
maintenance endpoint that reports counts, and the sync runner's `withdrawn_by_erp` audit
row for a system-actor lifecycle event recorded on the line.

## Goals / Non-Goals

**Goals:**

- Make a line's categorization status readable at a glance, distinguishing a failure from a
  backlog item.
- Give a management user a supported way to return failed lines to the categorizer.
- Keep the reset auditable and reversible in the sense that matters: the trail explains why
  a line moved backwards.
- Change no persisted schema.

**Non-Goals:**

- Improving the categorizer. The stub is a token-set intersection over English leaf names
  and will fail the same Danish and blank descriptions again; requeueing is the mechanism
  the improvement will need, not the improvement.
- Running categorization from the web API, synchronously or in a background task.
- Per-line requeue from the line editor. The company-wide action is what the reported
  problem needs; a per-line control can follow if it is ever asked for.
- Requeueing `ai_categorized` lines ("recategorize everything"). Different operation,
  different risk, and it would discard usable results.

## Decisions

### The endpoint queues; it does not categorize

`POST /companies/{id}/recategorize` sets `ai_failed` → `uncategorized` and returns a count.
The next `python -m ai_api.sync.runner` picks the lines up.

*Alternative considered:* have the endpoint invoke the categorizer directly. Rejected — it
inverts the package dependency the architecture is built on, and the categorizer's
candidate set comes from the company's spend tree via machinery that lives entirely in
`ai_api`.

*Alternative considered:* a background task or job queue in the web API. Rejected as
disproportionate: there is no job infrastructure today, and adding one to avoid a wording
problem in a dialog is the wrong trade. The honest framing — "queued for the next sync" —
costs one sentence of UI copy.

The naming follows from this. The endpoint and the menu item say *recategorize* because
that is the user's intent, and the confirmation dialog says *queued*, because that is the
mechanism. A dialog that promised immediate categorization would be a lie with an hour's
latency.

### Only `ai_failed` is eligible

`verified` is excluded because human review is authoritative. `ai_categorized` is excluded
because nothing failed, and including it would turn a repair action into a full
recategorization of the ledger. `uncategorized` is excluded from the *count* because it is
already queued and counting it would report work not done.

Origin is not a filter. An `entry_fallback` stand-in's spend is real spend, and on the dev
org stand-ins are most of the ledger — excluding them would make the action almost useless.

### The reset clears `error_message` and audits the transition

`error_message` describes an attempt that is no longer the line's state; leaving it beside
a queued line misreports it. The audit row (`requeued_for_categorization`, actor `system`)
carries the status change, mirroring how the sync records `withdrawn_by_erp`. This is the
only backwards transition in the lifecycle, so without the row a line that was `ai_failed`
yesterday and `uncategorized` today has no explanation.

Invoice rollups are recomputed in the same transaction via `web_api/rollup.py`, for the
same reason the withdraw path does it: an invoice must not claim to be categorized while
its lines are queued.

### Status is a column, stale is a marker inside it

A fifth pseudo-status "stale" was considered and rejected: `category_stale` is computed
(`any level set and no spend_category_id`) and orthogonal to the lifecycle — a line can be
`verified` **and** stale, which is precisely the case a reviewer must see. Rendering stale
as a status would erase whichever real status the line holds. It therefore renders as a
secondary marker within the same cell.

Only `ai_failed` is styled as a problem. Styling `uncategorized` as one too would flag most
of the ledger and make the signal worthless — the same reasoning the provenance mark
already follows for stand-in lines.

### Where the column goes

The status column is added to `LineHeaderRow`/`LineRow` in `voucher-table.tsx` and to the
drawer's Lines tab, which render the same `InvoiceLineRead`. A shared `LineStatusBadge`
component keeps the two from drifting, exactly as `SpendCategory` is already shared.

## Risks / Trade-offs

- **A user requeues and sees nothing change** → The dialog states that lines are queued for
  the next sync, and the result reports the count queued rather than implying
  categorization. This is the main UX risk and it is handled with copy, deliberately.
- **Requeueing repeatedly against an unimproved categorizer produces churn** → Each pass
  re-fails the same lines and writes fresh audit rows. Acceptable: the action is manual,
  management-gated, and its cost is bounded by the failed-line count. Not worth a cooldown.
- **A widened line table crowds on narrow viewports** → The table already scrolls
  horizontally in its own container; the status column is short-labelled.
- **`ai_failed` ceasing to be terminal weakens it as a signal** → Mitigated by the audit
  row: the transition is always attributable, and only an explicit request can cause it. A
  sync still never resets a failure on its own.

## Migration Plan

None. No schema change, no migration, no data backfill — `status` and `category_stale` are
already in the payload, and the endpoint is additive. The change is safe to deploy in
either order (frontend before backend just leaves the menu action failing until the
endpoint lands, so ship backend first).

## Open Questions

- Should the action also appear on the Entries page, scoped to the current filter, rather
  than only per company in Settings? Deferred — the company menu answers the reported need,
  and a filter-scoped variant raises "which lines exactly" questions the row menu does not.
- Should the result link to the queued lines (`/entries?status=uncategorized`)? Deferred to
  implementation; nice, not required by any scenario.
