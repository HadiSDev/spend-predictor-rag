## ADDED Requirements

### Requirement: Lines SHALL be filterable by whether the AI was confident

`GET /invoice-lines` SHALL accept a `needs_review` filter which, when true, returns only lines whose status is `ai_categorized` and whose `confidence` is below the platform's review threshold. When false or absent, the listing SHALL be unaffected.

A `verified` line SHALL never be returned by this filter whatever its confidence: a human has already looked, which is the entire question the filter asks. Lines that are `uncategorized` or `ai_failed` SHALL likewise be excluded — they are their own backlogs, already filterable by `status`, and folding them in would make one filter mean three different kinds of work.

#### Scenario: Doubtful AI lines are returned

- **WHEN** `GET /invoice-lines?needs_review=true` is called
- **THEN** only `ai_categorized` lines whose confidence is below the threshold are returned

#### Scenario: A verified line is excluded whatever its confidence

- **WHEN** a line was AI-categorized with low confidence and then verified by a human
- **THEN** it is not returned by `needs_review=true`

#### Scenario: Failures and backlogs are not folded in

- **WHEN** `needs_review=true` is called on a company holding `ai_failed` and `uncategorized` lines
- **THEN** neither is returned

#### Scenario: The filter composes with the others

- **WHEN** `needs_review=true` is combined with `company_id` and a date range
- **THEN** the result respects every filter and paginates as any other listing does

### Requirement: A line payload SHALL state whether it is awaiting review

Every line payload SHALL carry a computed flag saying whether that line falls in the review set, resolved server-side from its status and confidence against the current threshold.

It SHALL be computed on read and never stored, for the same reason `category_stale` is: the threshold is a tunable platform judgement, and a stored flag would be a snapshot of a setting rather than a fact about the line — silently wrong for every historical line the moment it moved.

#### Scenario: The flag rides on the line

- **WHEN** a line below the threshold is fetched
- **THEN** its payload states that it needs review, with no second request

#### Scenario: The flag follows the threshold, not a column

- **WHEN** the review threshold is changed
- **THEN** the flag on existing lines reflects the new threshold without any row being rewritten
