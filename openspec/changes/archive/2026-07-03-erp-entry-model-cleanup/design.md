## Context

`ErpEntry` is the atomic financial record. Today it carries `entry_date`
(sourced from the mock ERP's `date`, semantically the posting date) and a direct
`erp_integration_id` FK. But an entry also has `erp_account_id → ErpAccount`, and
`ErpAccount` already has a NOT NULL `erp_integration_id`; plus `company_id` on the
entry itself. So the integration link is derivable and the direct column is
redundant. The sync runner currently uses the direct column in one place —
`_categorize_pending` scopes an integration's invoices via
`ErpEntry.erp_integration_id == integration_id` — and sets it in
`_persist_entries`. The deterministic entry id is `_det_id("entry",
integration_id, erp_entry_id)`, computed from data available at persist time.

## Goals / Non-Goals

**Goals:**
- Name the ledger date unambiguously (`accounting_date`) so period reporting has
  a clear axis.
- Drop the redundant `erp_integration_id` from `ErpEntry` without losing the
  ability to scope entries to an integration.
- Keep sync idempotent and all existing entry behavior (voucher linkage,
  not-categorized, retention on disconnect) intact.

**Non-Goals:**
- Adding a separate document/transaction date distinct from the posting date
  (the ERP source exposes one date; revisit if a real connector provides both).
- Any change to how entries link to invoices (voucher/`source_invoice_id`) or to
  accounts.

## Decisions

### `entry_date` → `accounting_date` (rename, not add)
The existing value already is the posting date, so this is a pure rename across
the model, the `ErpEntryData` DTO, the mock mapping, the runner, the read schema,
and the entries endpoint ordering. The Alembic migration uses
`op.alter_column(..., new_column_name="accounting_date")` to preserve data.

### Drop `ErpEntry.erp_integration_id`; derive via the account
Remove the column, its FK, and the `ErpIntegration.erp_entries` back-reference.
Where the runner needs an integration's entries, it joins through `ErpAccount`:

    select(...).join(ErpAccount, ErpEntry.erp_account_id == ErpAccount.id)
               .where(ErpAccount.erp_integration_id == integration_id)

`_persist_entries` stops setting the column but keeps deriving the entry id from
`integration_id`, so re-syncs still upsert the same rows (idempotency preserved).
`company_id` stays on the entry (tenant scope is unchanged).

### Read contract
`ErpEntryRead` renames `entry_date` → `accounting_date` and drops
`erp_integration_id`. Both are breaking wire changes; acceptable pre-launch, and
the field set already excludes secrets/raw_json.

## Risks / Trade-offs

- **Breaking wire changes** (renamed date, removed integration id) → acceptable
  now; no external consumers yet. Called out in the proposal.
- **Extra join** to scope entries by integration → negligible; `erp_account_id`
  is indexed via its FK and the account set per integration is small.
- **Migration renames a column** → data-preserving with `alter_column`; the
  drop of `erp_integration_id` is reversible (downgrade re-adds a nullable
  column + FK, but historical integration values are not reconstructed).
