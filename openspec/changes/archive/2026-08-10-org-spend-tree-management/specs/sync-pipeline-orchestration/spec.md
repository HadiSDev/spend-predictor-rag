## ADDED Requirements

### Requirement: The categorizer's candidates come from the company's assigned spend tree

The sync runner SHALL build its categorization candidate set from the persisted nodes of the tree its company is assigned, not from a table hard-coded in `ai_api`. Each candidate SHALL carry the node's id, its materialized `level_1`..`level_4` path, and its matching text (name, code, description). A matched line SHALL therefore resolve its `spend_category_id` by node id directly, rather than by looking a `(level_2, level_3)` pair back up.

The built-in taxonomy SHALL survive only as the seed definition of the platform's default tree template. Two companies assigned different trees SHALL be categorized against different candidate sets within the same run.

#### Scenario: Candidates are the assigned tree's nodes

- **WHEN** an integration for a company assigned tree `T` is synced
- **THEN** every line it categorizes is matched against `T`'s nodes and any resolved `spend_category_id` names a node of `T`

#### Scenario: A four-level tree yields four-level results

- **WHEN** the assigned tree has `max_depth = 4` and a depth-4 node matches
- **THEN** the line's `level_1`..`level_4` are set from that node's path

#### Scenario: Different companies, different trees, one run

- **WHEN** one run syncs two integrations whose companies are assigned different trees
- **THEN** each integration's lines are categorized against its own company's tree only

### Requirement: A company with no usable tree fails categorization loudly, not silently

When the company of an integration being synced has no assigned tree and no default-template copy can be resolved for its organization, the run SHALL leave that integration's lines `uncategorized` and record the reason on the integration's `SyncState`, rather than falling back to a built-in taxonomy the customer never chose.

Ledger data SHALL still land: the failure is a categorization failure, not a sync failure, and the watermark SHALL advance as it would for any successful fetch.

#### Scenario: No tree, no invented categories

- **WHEN** a company's organization has no spend tree and none can be created
- **THEN** its lines remain `uncategorized`, the reason is recorded on the `SyncState`, and no category values are written

#### Scenario: The ledger still lands

- **WHEN** categorization is skipped for want of a tree
- **THEN** the fetched entries, invoices and lines are persisted and the watermark advances
