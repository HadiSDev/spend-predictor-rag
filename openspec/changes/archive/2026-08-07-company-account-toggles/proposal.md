## Why

A company's ERP chart of accounts is the control surface for what the product
ingests and how it reads it, and none of it is reachable from the app. The API
has offered `GET /erp-integrations/{id}/accounts`, `PATCH /erp-accounts/{id}` and
`POST /erp-integrations/{id}/refresh-accounts` since the integration work
landed; nothing calls them. Today the only way to deselect an account is a
manual `PATCH`.

Two settings hang off each account, and they are not the same kind of thing:

- **`sync_enabled`** decides whether the sync pulls that account's entries at
  all. Already ours, already preserved across refreshes.
- **`with_vat`** records whether an account is *assumed* to be VAT-inclusive.
  This is what tells the reconciliation how to read a parsed invoice: when a
  predicted total and a posted entry disagree, knowing the account's VAT
  assumption is what separates a **VAT difference** from a **total difference**.

That makes `with_vat` a judgement the customer owns, not metadata the ERP
dictates — and today it is silently overwritten from the ERP on **every account
refresh and every sync**. A user's setting would revert without explanation.

## What Changes

- Add **`/settings/companies/$companyId/accounts`**, reached from the company
  row's action menu: the integration's chart of accounts with a **Sync** toggle
  and a **VAT** toggle per account, a search box, bulk enable/disable over the
  current filter, and a **Refresh from ERP** action.
- **`with_vat` becomes user-owned.** The ERP's value seeds a newly discovered
  account, and from then on the customer's setting stands. Both writers must
  preserve it:
  - `web_api/routers/erp_integrations.py:refresh_accounts`
  - `ai_api/sync/runner.py:_persist_accounts`
  Fixing only the first would leave the sync reverting the toggle on the next
  run, which reads as "my setting randomly resets".
- The page SHALL state what each toggle actually does — turning Sync off stops
  future ingestion but does not delete already-synced entries, and the VAT flag
  is an assumption used when reconciling, not something that recomputes stored
  amounts.
- An integration with no accounts yet (a company created in Settings but never
  synced or refreshed) SHALL get an empty state that offers **Refresh from ERP**,
  rather than an empty table.

## Capabilities

### New Capabilities

*(none — the page is a section of the existing settings area, and every endpoint
it uses already exists.)*

### Modified Capabilities

- `domain-model`: `with_vat` changes from ERP-read metadata to a user-owned
  setting seeded from the ERP and preserved across refreshes and re-syncs —
  the same ownership rule `sync_enabled` already has.
- `web-api-erp-integration-management`: `refresh-accounts` currently refreshes
  `with_vat` as metadata; it must preserve it instead.
- `frontend-settings`: gains account selection and VAT assignment for a
  company's ERP integration.

## Impact

**Backend** — two one-line ownership fixes plus their tests:

- `web_api/routers/erp_integrations.py` — drop `with_vat` from the fields a
  refresh overwrites; still set it when inserting a new account.
- `ai_api/sync/runner.py` — same, in `_persist_accounts`.
- No schema change and no migration: the column, the read model
  (`ErpAccountRead`), and the update model (`ErpAccountUpdate`) already carry it.
- `erp-connector-interface` is untouched: the connector still reports the ERP's
  value, and that value still seeds a newly discovered account.

**Frontend**

- New `routes/_authed/settings/companies.$companyId.accounts.tsx` and
  `components/settings/accounts-panel.tsx`.
- New `lib/accounts.ts` (account list, toggle mutation, refresh mutation);
  `lib/types.ts` gains `ErpAccountRead` / `ErpAccountUpdate`.
- `components/settings/companies-panel.tsx` — a "Manage accounts" item in the
  row action menu, disabled for a company with no connected integration.

**Behavioural note worth stating plainly:** existing deployments have had
`with_vat` overwritten from the ERP on every sync, so today's stored values are
whatever the ERP last said. After this change the first customer edit sticks.
No backfill is needed or wanted — the ERP value remains the right starting point.

## Not in Scope

- No use of `with_vat` in reconciliation yet. This change makes the assumption
  recordable and durable; the comparison that consumes it (VAT difference vs
  total difference) is its own change.
- No per-account category mapping, no account hierarchy editing, no bulk import.
- No retroactive deletion of entries when an account is switched off — the
  toggle governs future ingestion only.
