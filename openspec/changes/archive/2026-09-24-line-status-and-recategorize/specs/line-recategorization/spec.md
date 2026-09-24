## ADDED Requirements

### Requirement: Failed lines can be returned to the categorizer's queue

The API SHALL expose `POST /api/v1/companies/{company_id}/recategorize`, which returns
that company's `ai_failed` invoice lines to `uncategorized` so the next sync run's
categorizer processes them again.

The endpoint SHALL be management-gated (system admin, or org `admin`/`moderator`), matching
`POST /companies/{id}/recompute-fx`, whose shape it mirrors. A company outside the caller's
tenant scope SHALL be a `404`, active or not — the same rule every other company-addressed
endpoint follows.

#### Scenario: Failed lines are queued

- **WHEN** a management caller posts to `/companies/{id}/recategorize` for a company with
  `ai_failed` lines
- **THEN** every one of those lines has status `uncategorized` and the response reports how
  many were queued

#### Scenario: A read-only role may not queue

- **WHEN** a caller with role `member` or `viewer` posts to the endpoint
- **THEN** the request is rejected as forbidden and no line's status changes

#### Scenario: Another organization's company is not reachable

- **WHEN** a caller posts to the endpoint for a company outside their tenant scope
- **THEN** the response is `404` and no line's status changes

#### Scenario: A deactivated company can still be requeued

- **WHEN** a management caller posts to the endpoint for a deactivated company in their org
- **THEN** the request succeeds, because a deactivated company's history is retained and
  addressing it by id is deliberate

### Requirement: Only AI failures are eligible

The endpoint SHALL reset **only** lines whose status is `ai_failed`.

- A `verified` line SHALL NOT be reset. A human's decision is authoritative, and requeuing
  it would hand the categorizer permission to overwrite the one categorization we trust.
- An `ai_categorized` line SHALL NOT be reset. Nothing failed; requeuing it would discard a
  usable result to re-derive it, and on a large ledger would recategorize everything.
- An `uncategorized` line SHALL NOT be counted. It is already queued, and counting it would
  report work the call did not do.

A line that is `ai_failed` SHALL be reset regardless of its `origin`. An `entry_fallback`
line's spend is real spend, and excluding stand-ins would leave most of the ledger
permanently unqueueable.

#### Scenario: A verified line is untouched

- **WHEN** the endpoint runs over a company holding `verified` lines
- **THEN** those lines keep status `verified` and are not counted in the result

#### Scenario: An already-categorized line is untouched

- **WHEN** the endpoint runs over a company holding `ai_categorized` lines
- **THEN** those lines keep status `ai_categorized` and their result fields are unchanged

#### Scenario: A stand-in line is eligible

- **WHEN** an `ai_failed` line with `origin = entry_fallback` is in scope
- **THEN** it is reset to `uncategorized` like any other failed line

#### Scenario: Nothing to do is success, not an error

- **WHEN** the endpoint runs over a company with no `ai_failed` lines
- **THEN** the response is `200` with a queued count of zero

### Requirement: A reset clears the failure and is audited

Resetting a line SHALL clear `error_message`, because the message describes an attempt that
is no longer the line's current state, and a stale failure shown beside a queued line
misreports it.

Each reset line SHALL append an `AuditLog` row with action `requeued_for_categorization`
and actor `system`, carrying the status transition. The reset is the only event that moves
a line backwards through the lifecycle, so the trail is what explains a line that was
`ai_failed` yesterday and `uncategorized` today.

The affected invoices' rolled-up `status` SHALL be recomputed in the same transaction, so
an invoice never claims to be categorized while its lines are queued.

#### Scenario: The reset is recorded

- **WHEN** a line is reset from `ai_failed` to `uncategorized`
- **THEN** an `AuditLog` row exists for that line with action `requeued_for_categorization`,
  actor `system`, and a change entry from `ai_failed` to `uncategorized`

#### Scenario: The stale failure message is cleared

- **WHEN** a line carrying an `error_message` is reset
- **THEN** its `error_message` is null

#### Scenario: The invoice rollup follows

- **WHEN** every categorized line of an invoice is reset
- **THEN** that invoice's status is recomputed to `uncategorized` in the same transaction

#### Scenario: A failure rolls back wholly

- **WHEN** the reset cannot be committed
- **THEN** no line's status, no `error_message`, no audit row, and no invoice rollup is
  persisted

### Requirement: The endpoint queues work, it never performs it

The endpoint SHALL NOT run the categorizer. `web_api` does not import `ai_api`, so
categorization happens only in the sync runner, on its own schedule.

The response SHALL therefore report what was queued rather than what was categorized, and
the API SHALL NOT report a categorization outcome it cannot know. The result SHALL carry
the company id and the number of lines queued.

#### Scenario: The response describes queueing

- **WHEN** the endpoint succeeds
- **THEN** the response reports the company id and a count of lines queued, and reports no
  categorization result

#### Scenario: No categorization happens during the request

- **WHEN** the endpoint returns
- **THEN** the reset lines have no category assigned and are waiting for the next sync run
