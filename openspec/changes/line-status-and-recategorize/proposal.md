## Why

A line's categorization status is invisible. The Entries page shows a **Spend category**
column, and a line the AI failed on renders exactly like a line nobody has tried yet —
both show `—`. On the dev org that is 28 lines out of 29, and no one looking at the page
can tell whether the categorizer ran and lost, has not run, or was never going to run
because the company has no spend tree. "I cannot see that the AI ran" is the report that
prompted this.

The second half is the way back. `ai_failed` is terminal: the sync's categorizer only
processes `uncategorized` lines, so once a line fails it is never retried — not by a
re-sync, not by `--since`, not by anything short of hand-written SQL. That was survivable
while the categorizer was a keyword stub nobody expected to improve, and stops being
survivable the moment it does improve, because there would be no way to let it try again
over the backlog it already lost.

## What Changes

- The Entries page's line rows gain a **Status** column reporting the categorization
  lifecycle — `uncategorized`, `ai_failed`, `ai_categorized`, `verified` — as a labelled
  badge, plus the computed `category_stale` state, which is neither a status nor a failure
  but does mean the line's decision no longer resolves.
- A **Recategorize failed lines** action on the company row menu in Settings, beside
  *Recompute currency figures*, which it deliberately mirrors.
- A new `POST /companies/{id}/recategorize` (management-gated) that returns `ai_failed`
  lines to `uncategorized` so the next sync's categorizer picks them up, audits each reset,
  and reports the count it queued.
- The endpoint **queues, it does not categorize.** `web_api` may not import `ai_api`, so
  no HTTP request can run the categorizer. Naming it after what it actually does is the
  point: a button that claimed to recategorize and then did nothing visible for an hour
  would be worse than no button.
- No new persisted column. `InvoiceLine.status` is already on `InvoiceLineRead`, so the
  status column is presentation over a field the API already sends.

## Capabilities

### New Capabilities

- `line-recategorization`: returning failed lines to the categorizer's queue — who may ask,
  which lines are eligible, what is audited, and what the caller is told.

### Modified Capabilities

- `frontend-erp-entries`: the line table gains a status column; requirements about what a
  line row shows change.
- `frontend-settings`: the company row menu gains an action; requirements about what that
  menu offers change.
- `categorization-lifecycle`: `ai_failed` stops being terminal — there is now a defined,
  audited transition back to `uncategorized`.

## Impact

- **Frontend**: `components/entries/voucher-table.tsx` (line header + row, new status
  badge), `components/settings/companies-panel.tsx` (menu item + confirm dialog),
  `lib/companies.ts` (mutation), `lib/types.ts` (result type), `routes/_authed/settings/
  companies.tsx` (wiring). Tests beside each.
- **Backend**: `routers/companies.py` (one endpoint), `schemas.py`
  (`RecategorizeResult`), `audit.py` usage only — no schema or migration change.
- **Not affected**: the sync runner, the categorizer, and `ai_api` generally. This change
  adds no path from the web API into the AI package and does not alter how a line is
  categorized once queued.
