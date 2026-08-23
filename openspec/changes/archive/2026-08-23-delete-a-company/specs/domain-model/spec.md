## ADDED Requirements

### Requirement: A company is deactivated by default and deleted only by a platform operator

`Company` SHALL remain soft-deactivated in the ordinary case: it owns financial
records, and retiring one from the listings SHALL NOT destroy them.

A system admin MAY additionally delete a company outright, destroying it and
every record scoped to it. That path exists for a company that should not exist —
created by mistake, a trial that never synced, a test tenant, or one a customer
has asked to have removed — and not for retiring a company whose ledger still
means something.

The two SHALL stay distinguishable in what they leave behind:

- A **deactivated** company still exists, keeps every record, stays reachable by
  id so its history loads, and can be reactivated.
- A **deleted** company does not exist, and nothing about it is recoverable.

`is_active` SHALL NOT be used to represent deletion. A flag that meant "retired"
in one place and "destroyed" in another would make every listing's meaning depend
on which one wrote it.

#### Scenario: Deactivation destroys nothing

- **WHEN** a company is deactivated
- **THEN** its invoices, lines and postings are all still present and it can be
  reactivated

#### Scenario: Deletion destroys everything it owns

- **WHEN** a system admin deletes a company
- **THEN** neither the company nor any record scoped to it remains

#### Scenario: The two states are not the same state

- **WHEN** a company is deleted
- **THEN** it is absent, not present with `is_active = false`
