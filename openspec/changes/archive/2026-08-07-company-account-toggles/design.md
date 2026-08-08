## Context

Every endpoint this page needs already exists and is tested; nothing calls them.
The work is a settings sub-route plus a correction to who owns `with_vat`.

The correction is the interesting part. `ErpAccount` carries three booleans with
three different owners, and only two of them are currently honoured:

| Field | Owner | Refresh behaviour today |
|---|---|---|
| `is_active` | the ERP | overwritten — correct |
| `sync_enabled` | us | preserved — correct |
| `with_vat` | *claimed* the ERP | overwritten — **wrong** |

The user's reason for owning `with_vat` is concrete: reconciliation compares a
parsed invoice against what the accountant posted, and the account's VAT
assumption is what decides whether a discrepancy is a VAT difference or a total
difference. That is a customer judgement about their own chart, not a fact the
ERP asserts — some ERPs do not report it at all, and `ErpAccountData.with_vat`
defaults to `false` when omitted, which would then be asserted as truth.

Constraints:

- **Two writers.** `refresh_accounts` (web_api) and `_persist_accounts`
  (ai_api). Both upsert accounts; both currently clobber. A fix in one place is
  not a fix.
- **`ai_api` imports `web_api`, never the reverse** — unchanged here.
- **Account ids are deterministic** (`_det_id("erp_account", integration_id,
  code)` in the runner), so upserts are idempotent and a preserved field stays
  attached to the right row across runs.
- **`GET /erp-integrations/{id}/accounts` is not management-gated** (it takes
  `tenant_scope`), while `PATCH /erp-accounts/{id}` requires management. Read and
  write are gated differently, and the page must reflect that.

## Goals / Non-Goals

**Goals:**

- Make the chart of accounts visible and editable from the app.
- Make `with_vat` a setting that survives — the whole point of recording it.
- Keep the two toggles legible as different things: one gates ingestion, the
  other describes an assumption.
- Work for a chart of 25 accounts and for one of several hundred.

**Non-Goals:**

- Consuming `with_vat` in any comparison. This change makes it durable and
  editable; the reconciliation that reads it is separate.
- Any schema change, migration, or backfill.
- Editing account names, codes, hierarchy, or `is_active` — those are the ERP's.
- Deleting or re-ingesting entries when a toggle changes.

## Decisions

### `with_vat` is seeded from the ERP, then owned by the customer

Not "ignore the ERP" and not "the ERP always wins". On **insert**, the ERP's
value is the best available starting guess. On **update**, it is left alone.

This is exactly `sync_enabled`'s rule with a different default — `sync_enabled`
defaults to `true`, `with_vat` defaults to whatever the ERP said — so the two
fields become one consistent concept ("ours, seeded differently") rather than
two special cases.

The ERP's current value is not lost by preserving ours: `raw_json` retains the
account payload each refresh, so the original is recoverable if a future change
wants to surface "the ERP now disagrees with your setting".

**Alternative considered:** a separate `erp_with_vat` column recording what the
ERP last said, so drift is visible in the UI. Rejected for now — it is a
migration and a second concept, and the drift signal has no consumer until the
reconciliation exists. `raw_json` already makes it recoverable.

### Both upsert sites change, and a test covers each

The failure this guards against is asymmetric and quiet: fix the API endpoint
only, and the toggle works until the next sync, then reverts. Fix the runner
only, and it reverts when someone hits Refresh. So the requirement is stated
once in `domain-model` (an ownership rule that binds any writer) and asserted
twice in tests — once per writer.

### The page is a route under the company, not a tab or a dialog

`/settings/companies/$companyId/accounts`. A real chart of accounts is hundreds
of rows with search and bulk actions; a drawer is too narrow for that and an
expandable table row nests a scroll region inside a table. A route is also
linkable, which matters when someone wants to point a colleague at a specific
company's setup.

It is reached from the company row's action menu ("Manage accounts"), alongside
Edit and Deactivate — and **disabled when the company has no connected
integration**, since there is no chart to manage.

### Toggles save immediately, per account, with the row as the unit

No form, no Save button. Each switch issues its own `PATCH /erp-accounts/{id}`
and the row reflects the server's answer. A chart of accounts is reviewed by
scanning and flipping a few switches; batching that behind a save button invites
half-finished edits and makes the failure mode ("which of my 12 changes failed?")
much worse.

A failed toggle reverts the switch and surfaces the error against that row, so
the UI never claims a setting that did not persist.

### Bulk actions operate on the current filter, and say so

"Enable all" / "Disable all" apply to the **rows currently visible**, not the
whole chart. Acting on hidden rows is how a user disables 300 accounts by
accident. The control states the count it will affect ("Enable 19 shown"), and
issues one `PATCH` per row — there is no bulk endpoint and inventing one is out
of scope for a list this size.

### Refresh is explicit, and reports what it did

`POST /erp-integrations/{id}/refresh-accounts` returns `{seen, added}`. The page
reports both ("25 seen, 3 added") rather than silently refetching, because the
useful information is whether the ERP has grown — and because a refresh that
adds nothing should visibly do nothing rather than look broken.

### Read and write are gated differently, and the page follows

`GET .../accounts` needs only tenant scope; `PATCH /erp-accounts/{id}` and
`refresh-accounts` need management. A `member` or `viewer` therefore sees the
chart read-only, with the switches disabled and the reason stated — the same
pattern the rest of the settings area already uses (`canManageCompanies`).

## Risks / Trade-offs

- **Existing `with_vat` values are whatever the ERP last said**, since every sync
  has been overwriting them. → That is the correct starting point, so no backfill.
  Stated in the proposal so it is not mistaken for data loss.
- **One request per toggle** means a bulk action over 300 rows issues 300
  requests. → Bulk is scoped to the visible filter, and the count is shown before
  acting. A bulk endpoint is the fix if real charts make this hurt.
- **Turning off `sync_enabled` leaves already-synced entries in place**, so the
  Entries page still shows them. → Correct (deleting financial history from a
  toggle would be worse), but non-obvious, so the page says it explicitly.
- **`with_vat` has no consumer yet.** Making it editable before anything reads it
  risks users setting it and seeing no effect. → The page describes it as an
  assumption recorded for reconciliation rather than implying an immediate
  effect. The alternative — waiting for the consumer — leaves the field being
  silently clobbered in the meantime.
- **The mock ERP reports `with_vat` for all 25 accounts**, so the seeded values
  look authoritative in dev. A real connector may omit it entirely and default
  everything to `false`. → Exactly why the customer needs to own it.

## Migration Plan

No schema change, no migration, no backfill. Deploy order does not matter: the
backend fix is invisible until someone edits a value, and the frontend route is
inert without it. Rollback is reverting the commit; stored values are unaffected
either way.

## Open Questions

- Should the page show when the ERP's reported `with_vat` disagrees with the
  customer's setting? `raw_json` makes it recoverable, but there is no consumer
  for the signal until the reconciliation lands. Revisit then.
- Should switching `sync_enabled` off offer to hide that account's existing
  entries from the Entries page? Leaving history visible is the safe default;
  whether it is the *wanted* one is worth asking once someone has actually
  deselected an account in anger.
