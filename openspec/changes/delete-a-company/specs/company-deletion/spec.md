## ADDED Requirements

### Requirement: A company can be deleted with everything it owns

A system admin SHALL be able to delete a company, removing it and every record
scoped to it, in one transaction.

Deletion is for a company that should not exist — created by mistake, a trial
that never synced, a test tenant, or one a customer has asked to have removed.
It is not the way to retire a company whose ledger still means something:
deactivation exists for that, is reversible, and remains the default.

The following SHALL be destroyed: the company, its ERP integrations and their
credentials, accounts and sync state, its files, its invoices and invoice lines,
its ERP entries, its recommendations, and the audit rows describing the invoices
and lines that were destroyed.

#### Scenario: The company and its records are gone

- **WHEN** a system admin deletes a company holding invoices, lines, postings and
  a connected integration, with confirmation
- **THEN** no row referencing that company remains in any of those tables, and
  the company itself is gone

#### Scenario: Deletion is one transaction

- **WHEN** the deletion fails partway through for any reason
- **THEN** nothing is removed, and the company is exactly as it was

#### Scenario: A company that owns nothing deletes too

- **WHEN** a system admin deletes a company with no invoices and no postings
- **THEN** it is deleted, with no confirmation required

### Requirement: Deletion requires a system admin

The endpoint SHALL be restricted to a platform system admin
(`User.is_system_admin`). An organization admin or moderator SHALL receive `403`.

Deactivation is reversible and belongs to whoever manages the organization.
Destroying a ledger cannot be undone by a support conversation, so it belongs to
the operator holding the platform flag.

#### Scenario: A system admin may delete

- **WHEN** a system admin deletes a company
- **THEN** the request succeeds

#### Scenario: An organization admin may not

- **WHEN** an org admin deletes a company in their own organization
- **THEN** the request is refused with `403` and nothing is removed

#### Scenario: A moderator, member or viewer may not

- **WHEN** any non-system-admin role attempts the deletion
- **THEN** the request is refused with `403`

### Requirement: Deletion is refused until confirmed, and the refusal says what would be lost

When the company holds any financial record, the request SHALL be refused with
`409` unless it carries an explicit confirmation.

The refusal SHALL carry what would be destroyed — the number of invoices, invoice
lines, ERP entries and integrations, and the earliest and latest accounting date
covered. A count is what makes the difference between "some data" and "four
years of a live tenant" visible before the fact, and the date span is what makes
the company recognisable when its name is not.

A refused request SHALL change nothing.

#### Scenario: An unconfirmed deletion is refused with the figures

- **WHEN** a system admin deletes a company holding 203 invoices, 398 lines and
  963 postings without confirming
- **THEN** the response is `409` carrying those counts and the accounting date
  span, and the company still exists

#### Scenario: A confirmed deletion proceeds

- **WHEN** the same request is repeated with confirmation
- **THEN** the company and its records are deleted

#### Scenario: A refusal is not a partial deletion

- **WHEN** a deletion is refused for want of confirmation
- **THEN** every invoice, line and posting is still present

### Requirement: The global supplier catalog survives a deletion

`Vendor` rows SHALL NOT be deleted, including any left referenced by no invoice.

The catalog is global and shared across tenants: a supplier is not the deleted
company's to remove, and another organization may already reference the same row.
A vendor nothing points at is not an orphan — it is a supplier nobody has bought
from yet, which is the state every vendor starts in.

#### Scenario: A supplier only this company referenced is kept

- **WHEN** a company whose invoices were the only ones referencing a vendor is
  deleted
- **THEN** that vendor still exists

#### Scenario: Another tenant's view is unaffected

- **WHEN** a company is deleted
- **THEN** vendors referenced by other organizations' invoices are untouched

### Requirement: The organization's spend trees survive a deletion

A `SpendTree` SHALL NOT be deleted with a company assigned to it, nor SHALL its
nodes.

A tree belongs to the organization, and several companies may share one — a
bookkeeping firm running one taxonomy across its clients is the case the design
exists for. Taking the tree with one of them would silently recategorize the
others.

#### Scenario: A shared tree survives

- **WHEN** one of two companies sharing a spend tree is deleted
- **THEN** the tree and its nodes still exist and the other company is still
  assigned to it

#### Scenario: A tree assigned to nothing still survives

- **WHEN** the only company assigned to a tree is deleted
- **THEN** the tree still exists, now assigned to no company

### Requirement: A deleted company is unreachable, not hidden

After deletion the company's id SHALL NOT appear in the caller's tenant scope,
and every route resolving a company by id SHALL return `404` for it.

This is the difference from deactivation, which deliberately keeps a company
reachable by id so its history loads and it can be reactivated. There is no
history to load and nothing to reactivate.

#### Scenario: Fetching the deleted company by id

- **WHEN** any caller requests the deleted company by id
- **THEN** the response is `404`

#### Scenario: Listings no longer offer it

- **WHEN** the company list is requested, including with inactive companies
- **THEN** the deleted company does not appear

#### Scenario: Its records do not appear in reports

- **WHEN** a report is requested across the organization after the deletion
- **THEN** none of the deleted company's spend is counted
