## ADDED Requirements

### Requirement: Line payloads carry the fourth level and their resolution state

`InvoiceLineRead` SHALL carry `level_4` beside `level_1`..`level_3`, and SHALL carry a boolean `category_stale` that is true when the line has categorization levels set but its `spend_category_id` does not name a node of the company's currently assigned spend tree.

`category_stale` SHALL be computed server-side. A client cannot know which tree a company is assigned without a second request, and a stale category presented as a settled one is the failure this whole change exists to prevent.

#### Scenario: The fourth level is readable

- **WHEN** a line categorized against a four-level tree is read
- **THEN** its payload carries `level_4`

#### Scenario: A stale category is flagged

- **WHEN** a line has `level_2` set and a null `spend_category_id` after its company's tree changed
- **THEN** its payload reports `category_stale: true`

#### Scenario: An uncategorized line is not stale

- **WHEN** a line has never been categorized
- **THEN** its payload reports `category_stale: false`

### Requirement: Verification accepts a node or explicit levels

`POST /api/v1/invoice-lines/{id}/verify` SHALL accept `level_4` in addition to the existing correction fields, and SHALL accept a `spend_category_id`.

- When `spend_category_id` is supplied, the server SHALL resolve that node within the company's assigned tree and set `level_1`..`level_4` from its materialized path, ignoring any level values the caller also sent — the node is the authority.
- When `spend_category_id` names a node that does not exist or belongs to a tree the company is not assigned, the API SHALL respond `422 Unprocessable Entity` and change nothing.
- `level_4` SHALL be part of the audited field set, so a change to it appears in the line's audit trail.

#### Scenario: A node correction wins over sent levels

- **WHEN** a manager verifies a line sending both a `spend_category_id` and a conflicting `level_2`
- **THEN** the stored levels are the node's path and the response reflects them

#### Scenario: An unknown node is rejected

- **WHEN** a verify names a `spend_category_id` that does not exist
- **THEN** the API responds `422 Unprocessable Entity` and the line keeps its previous state

#### Scenario: A node from another tree is rejected

- **WHEN** a verify names a node belonging to a tree the line's company is not assigned
- **THEN** the API responds `422 Unprocessable Entity` and the line is unchanged

#### Scenario: level_4 is audited

- **WHEN** a manager verifies a line changing only `level_4`
- **THEN** the action is recorded as an `edit` and the audit entry carries the `level_4` change

### Requirement: Lines can be filtered by category staleness

`GET /api/v1/invoice-lines` SHALL accept a `stale` boolean filter selecting lines whose stored categorization no longer resolves within their company's assigned tree, so a reviewer can work the backlog a tree change created without scanning every page.

#### Scenario: Filtering to the stale backlog

- **WHEN** a client requests `/api/v1/invoice-lines?stale=true`
- **THEN** the page contains only lines with categorization levels set and no resolving `spend_category_id`

#### Scenario: The filter is tenant-scoped like every other

- **WHEN** the filter is applied without a `company_id`
- **THEN** it covers the caller's active companies only, exactly as the unfiltered listing does
