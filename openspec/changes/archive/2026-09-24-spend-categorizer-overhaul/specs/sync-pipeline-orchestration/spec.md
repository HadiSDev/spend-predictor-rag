## ADDED Requirements

### Requirement: The runner SHALL carry every line field the categorizer reads, and a test SHALL pin the mapping

The runner's `InvoiceLine` → categorization-context mapping SHALL carry the line's **item name** as the primary statement of what was bought, its description as supplementary detail, its native account code and that account's name, its invoice's supplier and currency, and its amount.

A test SHALL exercise that mapping **through the runner**, from a persisted `InvoiceLine` to the text the model is shown. Every existing categorizer test constructs the context by hand, which is exactly why the field could be renamed out from under the runner without a single test turning red: the line kept its text, the prompt lost it, and the model correctly reported that it had been told nothing.

#### Scenario: A persisted line's name reaches the prompt

- **WHEN** the runner categorizes a persisted line whose `item_name` is "DJI Osmo Nano actionkamera 128GB" and whose `description` is null
- **THEN** the prompt the model receives contains that item name

#### Scenario: The mapping is asserted, not mirrored

- **WHEN** a field the categorizer reads is renamed on `InvoiceLine`
- **THEN** the runner mapping test fails

#### Scenario: The account's name travels with its code

- **WHEN** a line was posted to an account whose ERP name is "Edb-udgifter / software"
- **THEN** the prompt states that name and not only the bare account code

## MODIFIED Requirements

### Requirement: The categorizer's candidates come from the company's assigned spend tree

The sync runner SHALL build its categorization candidate set from the persisted nodes of the tree its company is assigned, not from a table hard-coded in `ai_api`. Each candidate SHALL carry the node's id, its materialized `level_1`..`level_4` path, and its matching text (name, code, description). A matched line SHALL therefore resolve its `spend_category_id` by node id directly, rather than by looking a `(level_2, level_3)` pair back up.

The built-in taxonomy SHALL survive only as the seed definition of the platform's default tree template. Two companies assigned different trees SHALL be categorized against different candidate sets within the same run.

The candidate set MAY be **narrowed within that tree** by retrieval before it is offered to the model — see `spend-categorization-model`. Narrowing SHALL only ever remove nodes of the company's own tree; it SHALL NOT introduce a node from anywhere else, and when retrieval is unavailable the full leaf set of the assigned tree SHALL be offered instead.

#### Scenario: Candidates are the assigned tree's nodes

- **WHEN** an integration for a company assigned tree `T` is synced
- **THEN** every line it categorizes is matched against `T`'s nodes and any resolved `spend_category_id` names a node of `T`

#### Scenario: A four-level tree yields four-level results

- **WHEN** the assigned tree has `max_depth = 4` and a depth-4 node matches
- **THEN** the line's `level_1`..`level_4` are set from that node's path

#### Scenario: Different companies, different trees, one run

- **WHEN** one run syncs two integrations whose companies are assigned different trees
- **THEN** each integration's lines are categorized against its own company's tree only

#### Scenario: Narrowing never leaves the assigned tree

- **WHEN** retrieval narrows the candidates for a line
- **THEN** every candidate offered is a node of that company's assigned tree
