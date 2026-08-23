## Context

A survey of what a company actually owns, verified against the running database:

**Six tables carry a `NOT NULL` `company_id`** — `erp_integrations`, `files`,
`invoices`, `invoice_lines`, `erp_entries`, `recommendations`. Three more are
reachable only through a parent: `erp_accounts` and `sync_state` through the
integration, `erp_credentials` through it as well.

**There are no cascades.** `grep -rn "ondelete" src/web_api/db/` returns nothing,
and `information_schema` agrees: every foreign key into `companies`, `invoices`
and `invoice_lines` is `NO ACTION`. A bare `DELETE FROM companies` fails today
with a foreign-key violation. The one exception in the whole schema is
`line_ground_truth.invoice_line_id`, which really is `CASCADE`.

**The ORM cannot do it either.** No `Company` relationship declares
`cascade_delete`, so `session.delete(company)` would try to null the children's
`company_id` — every one of which is `NOT NULL`.

**Every company has children.** `POST /companies` writes the company and its
`ErpIntegration` in one transaction, so no company created through the API is
ever childless. A "delete only if it owns nothing" rule would therefore refuse
every company in existence.

**`AuditLog` has no company anchor at all** — no foreign key, no `company_id`,
only `entity_type` and `entity_id` as plain strings. Its own module docstring
says tenancy "is derived through the referenced entity's company", and that rows
"are never updated or deleted".

## Goals / Non-Goals

**Goals:**

- A system admin can remove a company and everything it owns, in one
  transaction, with no dangling rows.
- Nothing is destroyed without the operator being shown what it is first.
- The global supplier catalog and the organization's spend trees are untouched.
- Deactivation stays the default, and the reason to prefer it stays written down
  next to the thing that overrides it.

**Non-Goals:**

- Undo. A deleted company is gone; deactivation is the reversible option and
  already exists.
- Deleting an organization or a user. `DELETE /api/v1/organization` already
  exists and deliberately soft-suspends.
- Cascading at the database level. See D2.
- Bulk deletion. One company, named explicitly, per request.

## Decisions

### D1 — Hard delete, not another flavour of soft

The user asked for "delete everything except scraped suppliers", and the whole
point is that the rows stop existing. A second tombstone state beside
`is_active=false` would give the operator a company that is even more hidden and
a database that is exactly as full — which is precisely the problem with the
`Test` company today.

*Alternative considered:* delete only companies that own nothing. Rejected on a
fact: `POST /companies` always creates an integration, so that rule refuses
every company the API has ever made. It would have been a safe-sounding endpoint
that never fires.

### D2 — Explicit ordered deletion, not `ON DELETE CASCADE`

The purge is a function that names every table it empties, in dependency order:

```
audit rows for the company's invoices and lines
erp_entries          (before invoices: its source_invoice_id points at them)
invoice_lines        (line_ground_truth follows by its own CASCADE)
invoices             (before files: invoice.file_id points at them)
files
recommendations
sync_state, erp_credentials, erp_accounts
erp_integrations
companies
```

Adding `ondelete="CASCADE"` to six foreign keys would be less code and is the
wrong trade. It makes *every* future delete of a company silent — including one
typed into a shell by mistake, or one a later feature performs without realising
what hangs off it. Written out, the blast radius is one function a reviewer can
read, and adding a table that hangs off a company means adding a line to it. The
cost is that a table added later and *not* added here fails loudly on a
foreign-key violation, which is the right way round.

*Consequence, accepted:* no `company_id` column is indexed, so each statement is
a sequential scan. At this scale (963 postings for the largest tenant) that is
irrelevant, and adding six indexes to serve an occasional admin action would be
paying continuously for something used rarely.

### D3 — Audit rows for deleted entities are deleted

This is the one genuinely uncomfortable decision, because `AuditLog` says it is
append-only and means it.

The rows in question describe invoices and lines that will not exist. They carry
no `company_id` and no foreign key, so nothing in the database would stop them
being left behind — and nothing would ever resolve them again either. Their only
tenancy anchor is the entity, so once it is gone they cannot be attributed to an
organization, filtered out of an admin feed, or answered for in a data-removal
request. They are not history at that point; they are a permanent leak of one
tenant's field-level values into a table nobody can scope.

So the contract is narrowed rather than broken: **an audit row is never
rewritten, and is removed only when the entity it describes is itself
destroyed.** Nothing else in the system destroys an entity — extraction
supersedes lines and records the removal, deactivation removes nothing — so this
path is the only one that can reach the clause.

*Alternative considered:* keep them. Rejected as above. *Alternative considered:*
give `AuditLog` a `company_id` so the rows could be retained and scoped. That is
a migration plus a backfill plus a write-path change on every audit site, to
retain history for a company the operator has just asked to erase.

### D4 — What survives, and why

**Vendors.** `Vendor` is global and shared across tenants; it carries no
`company_id` and no ERP identity. Deleting the invoices simply removes the
references. A vendor left referenced by nothing is not an orphan — it is a
supplier nobody has bought from yet, and another organization may already be
looking at it. Explicitly requested, and correct anyway.

**Spend trees.** A `SpendTree` belongs to the organization, and several companies
may share one — a bookkeeping firm running one taxonomy across its clients is
the case the design was built for. Deleting a company assigned to a tree must
leave the tree alone. `DELETE /spend-trees/{id}` already refuses while a company
is assigned, and after this delete one fewer is.

**The organization and its users.** Out of scope, and already have their own
endpoint.

### D5 — System admin only

`deps.py` has `require_management` (admin, moderator, or system admin) and
`require_org_admin` (admin or system admin). Neither is narrow enough, so this
adds `require_system_admin`.

An org admin deactivating their own company is reversible and theirs to do. An
org admin destroying their own ledger is not something a support conversation can
undo, and the operator who can help is the one holding the platform flag.

### D6 — The confirmation carries the counts, and the name arms it

Two precedents exist. `DELETE /spend-trees/{id}` takes `confirm` as a query
param and returns a plain-string 409; `POST /erp-integrations/{id}/replace`
takes it in the body and returns a typed model with counts and a date span.

This follows the second. The operator's question is "how much am I about to
destroy, and is it the company I think it is?", and a sentence cannot answer it
as well as figures can. The 409 body carries the invoice, line, posting and
integration counts plus the earliest and latest accounting date, so the span is
recognisable.

On the frontend the dialog additionally requires typing the company's name. A
checkbox is a reflex; a name is a second look at *which* company. This is the
only destructive action in the product with no undo, so it is the only one that
gets that treatment.

## Risks / Trade-offs

**An operator deletes the wrong company** → Mitigated by the system-admin gate,
the 409 preview with counts, and name-to-confirm in the UI. Not fully
mitigable — that is the nature of the feature, which is why deactivation stays
the default and the endpoint says so.

**A table added later is not added to the purge** → It fails loudly with a
foreign-key violation rather than silently orphaning, which is the deliberate
consequence of D2. A test asserts the company's tables are empty afterwards, so
a forgotten table shows up as a failure rather than as residue.

**The delete is not atomic across the FX cache or Qdrant** → Neither is
company-scoped. `fx_rates` is global reference data and the vector index is keyed
by spend tree, not company. Nothing to clean.

**Long transaction on a large tenant** → 963 postings today. If a tenant ever
reaches millions, this wants batching and the indexes D2 declines. Noted, not
solved; the endpoint is an occasional admin action, not a background job.

**A concurrent sync writes rows mid-delete** → The sync discovers work from
`ErpIntegration` rows, which the same transaction removes, so a run starting
after the commit finds nothing. A run already in flight could in principle insert
against a deleted company and fail its own foreign key, which isolates to that
integration and is recorded on its `SyncState` — the behaviour a failed
integration already has.

## Migration Plan

No schema change and no data migration. The endpoint is additive; nothing
existing changes behaviour. Rollback is reverting the code — with the obvious
caveat that a company already deleted stays deleted, which is what "no undo"
means.

Deploy order does not matter: the frontend hides the action from anyone without
the platform flag, and the backend enforces it independently.

## Open Questions

- Should deleting a company that is a customer's *only* company be refused,
  leaving an organization with none? Left permitted: an org with no companies is
  already reachable today by deactivating the last one.
- **`line_ground_truth` is in no migration.** It exists on the live database
  because `create_all()` made it, and `information_schema` confirms its
  `ON DELETE CASCADE` is real there — but a database built purely by
  `alembic upgrade head` would not have the table at all. That is harmless for
  this change either way (no table means nothing to cascade, and the purge still
  succeeds), but it is a genuine gap in `ai_api`'s own store and worth closing
  separately. Found while trying to test the cascade end to end.
- **Neither test suite enforces foreign keys.** Both run on SQLite with no
  `PRAGMA foreign_keys=ON`, so no cascade fires and no violation is raised in
  tests. That is why the cascade is pinned as a declaration rather than
  exercised as behaviour, and why the "a forgotten table fails loudly" guarantee
  in D2 holds on PostgreSQL but not in CI. Turning the pragma on would be a
  real improvement and a change of its own — it would likely surface existing
  fixtures that lean on lax foreign keys.
- Should the deletion itself be recorded somewhere — an operator-facing log
  outside `AuditLog`, which by D3 is the wrong table for it? Worth a follow-up if
  this is used more than rarely.
