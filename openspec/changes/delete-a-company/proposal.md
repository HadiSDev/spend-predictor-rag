## Why

There is no way to remove a company. `POST /companies/{id}/deactivate` retires
one from the pickers and the listings, and that is the right answer whenever the
company's ledger still means something — but it is the *only* answer, and some
companies should not exist at all.

This deployment has one right now. The `Test` company holds **175 of the 203
invoices** in the database, every one of them pending against a mock ERP that no
longer answers, and every document run that is not explicitly scoped picks its
invoices first and fails them on connection timeouts. It is not retired history
worth keeping; it is a wrong row that costs real time on every unscoped run.
Deactivating it hides it from a picker and changes none of that.

The same need arrives from three other directions: a company created with a
typo, a trial tenant that never synced, and a customer asking for their data to
be removed rather than merely hidden.

**This reverses a stated rule**, and deliberately. `Companies are soft-deactivated,
never hard-deleted` appears in `CLAUDE.md`, in `company.py`, in `deps.py`, in the
spend-tree service's own docstring, and in two tests' prose. The rule is sound
and stays the default — what changes is that it stops being the *only* option
for a platform operator holding a company that should never have existed.

## What Changes

- **New** `DELETE /companies/{id}`, restricted to **system admins**. Not
  `require_management`: an org admin may deactivate, but destroying financial
  records is a platform action.
- **Refused until confirmed.** Without `confirm=true` the endpoint returns `409`
  carrying what would be destroyed — invoices, lines, postings, integrations and
  the date span they cover — following `POST /erp-integrations/{id}/replace`,
  which already refuses with a typed body of counts.
- **The delete is explicit and ordered**, in one transaction: postings, lines,
  invoices, files, recommendations, sync state, credentials, accounts,
  integrations, then the company. There are no database cascades to lean on —
  verified against the live schema, every foreign key to `companies.id` is
  `NO ACTION`, so a bare `DELETE` fails today with a foreign-key violation.
- **BREAKING (policy)**: a deleted company is unrecoverable. Its id leaves
  `TenantScope.company_ids`, so every route that resolves a company by id returns
  `404` — including the "asking by id still works" guarantee that deactivation
  deliberately preserves.
- **Suppliers survive.** `Vendor` is a global catalog shared across tenants, and
  a supplier is not the deleted company's to remove. Rows left referenced by no
  invoice stay; an unreferenced vendor is not an orphan, it is a supplier nobody
  has bought from yet.
- **Spend trees survive.** A tree belongs to the *organization* and several
  companies may share one, so deleting a company assigned to it must not take it.
- **Audit rows for the deleted entities are deleted with them**, which amends
  `AuditLog`'s append-only contract for this one path. See the design: the
  alternative leaves rows that can never again be attributed to anyone.
- **Frontend**: a delete action on the company row in Settings, shown only to a
  system admin, with a confirmation naming the company and the counts, and typing
  the company's name to arm it.

## Capabilities

### New Capabilities

- `company-deletion`: removing a company and everything it owns — who may do it,
  what is destroyed, what deliberately survives, how the confirmation gate works,
  and what the ledger looks like afterwards.

### Modified Capabilities

- `domain-model`: the soft-deactivation rule gains its one exception, stated
  where the rule is stated so the two cannot be read apart.
- `web-api-company-management`: the new endpoint, its system-admin gate, and its
  confirmation contract.
- `audit-log`: the append-only guarantee is scoped — rows are never rewritten,
  and are removed only when the entity they describe is itself destroyed.
- `frontend-settings`: the company row gains a delete action for system admins.

## Impact

**Backend** — `routers/companies.py` (the endpoint), a new
`web_api/company_deletion.py` owning the ordered purge and the counts,
`schemas.py` (a typed 409 body and a result), and `deps.py` if a
`require_system_admin` gate does not already exist (it does not; `deps.py` has
`require_management` and `require_org_admin` only).

**Database** — no migration. The purge is explicit rather than delegated to
`ON DELETE CASCADE`: adding cascades to six foreign keys would make *every*
future company delete silent and unreviewable, including one issued by accident
from a shell. The blast radius stays written down in one function.

**`ai_api`** — nothing. `line_ground_truth` already declares `ON DELETE CASCADE`
on `invoice_line_id` and the live schema confirms it, so deleting a line takes
its ground truth with it without `web_api` importing `ai_api` — which it may not
do.

**Frontend** — `settings/companies-panel.tsx`, and `lib/companies.ts` for the
mutation.

**Not affected** — reporting, FX, the sync runner and the document stage all
scope by company and simply stop seeing one that no longer exists.
