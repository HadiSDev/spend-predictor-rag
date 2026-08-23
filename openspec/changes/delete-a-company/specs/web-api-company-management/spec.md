## ADDED Requirements

### Requirement: Delete a company

The API SHALL provide `DELETE /api/v1/companies/{id}`, restricted to a platform
system admin, which destroys the company and every record scoped to it in one
transaction.

- The caller MUST hold `is_system_admin`. An org `admin` or `moderator` — who may
  deactivate — SHALL receive `403`.
- When the company holds any invoice, line, posting or integration, the request
  SHALL be refused with `409` unless it carries `confirm=true`. The refusal body
  SHALL carry the counts and the earliest and latest accounting date.
- A company holding nothing SHALL delete without confirmation: there is nothing
  to preview and a gate would be ceremony.
- A refused request SHALL change nothing.
- The response SHALL report what was destroyed, so the caller's record of the
  action does not depend on having read the refusal first.

#### Scenario: A system admin deletes a company with records

- **WHEN** a system admin sends the request with `confirm=true` for a company
  holding invoices and postings
- **THEN** the company and its records are destroyed and the response reports the
  counts

#### Scenario: Without confirmation the request is refused

- **WHEN** the same request is sent without `confirm`
- **THEN** the response is `409` carrying the invoice, line, posting and
  integration counts and the accounting date span, and nothing is removed

#### Scenario: An org admin is refused

- **WHEN** an org admin sends the request for a company in their organization
- **THEN** the response is `403` and nothing is removed

#### Scenario: An empty company needs no confirmation

- **WHEN** a system admin deletes a company with no invoices and no postings and
  no `confirm`
- **THEN** the company is deleted

#### Scenario: A company in another organization

- **WHEN** a system admin deletes a company in an organization other than their
  own
- **THEN** it is deleted, since a system admin acts across organizations

#### Scenario: Deleting an unknown company

- **WHEN** the id names no company
- **THEN** the response is `404`
