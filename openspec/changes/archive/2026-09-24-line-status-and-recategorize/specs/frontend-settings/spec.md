## ADDED Requirements

### Requirement: Failed lines can be requeued from the company row menu

The Companies section's row menu SHALL offer a **Recategorize failed lines** action,
alongside *Recompute currency figures*, calling
`POST /api/v1/companies/{id}/recategorize`.

The two actions are deliberately siblings: both are company-scoped maintenance a customer
runs after something upstream changed, both report a count rather than changing what is on
screen, and both are management-gated.

- The action SHALL be hidden or disabled for a caller without management rights, following
  the section's existing role gating. A control that is present but will always fail claims
  a permission that will never be granted.
- The action SHALL confirm before running, stating that it queues lines rather than
  categorizing them, and SHALL report the number queued when it completes.
- The action SHALL surface a failure as a failure, and SHALL NOT report success when the
  request fails — the section's existing save-and-feedback rule.

#### Scenario: The action is offered

- **WHEN** a management user opens a company's row menu
- **THEN** a "Recategorize failed lines" action is offered

#### Scenario: A read-only user is not offered it

- **WHEN** a user without management rights opens a company's row menu
- **THEN** the action is absent or disabled

#### Scenario: The confirmation says what will happen

- **WHEN** the user activates the action
- **THEN** they are asked to confirm, and told that the lines are queued for the next sync
  rather than categorized now

#### Scenario: The result reports the count

- **WHEN** the request succeeds
- **THEN** the number of lines queued is reported to the user

#### Scenario: Nothing to requeue is stated plainly

- **WHEN** the request succeeds with a queued count of zero
- **THEN** the user is told no failed lines were found, not that work was done

#### Scenario: A failure is not reported as success

- **WHEN** the request fails
- **THEN** the error is surfaced and no success message is shown
