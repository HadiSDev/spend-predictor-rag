## ADDED Requirements

### Requirement: A line's category resolves within the company's assigned tree

The accepted `spend_category_id` on an `InvoiceLine` SHALL name a node of the tree its company is currently assigned. A categorization — AI or human — SHALL NOT set `spend_category_id` to a node of any other tree, and an attempt to do so SHALL be rejected rather than stored.

When a line's stored `spend_category_id` is null but its `level_*` values are set, the line SHALL be readable as categorized-but-unresolved: the decision stands, it just does not currently point at a node.

#### Scenario: The AI resolves within the assigned tree

- **WHEN** the sync categorizes a line for a company assigned tree `T`
- **THEN** any `spend_category_id` it writes belongs to `T`

#### Scenario: A correction outside the tree is rejected

- **WHEN** a manager verifies a line naming a `spend_category_id` from a tree the company is not assigned
- **THEN** the API responds `422 Unprocessable Entity` and the line is unchanged

### Requirement: A category that no longer resolves is stale, never rewritten

When a company's assigned spend tree changes, every line of that company whose `spend_category_id` names a node outside the new tree SHALL have that pointer cleared while every other categorization field — `level_1`..`level_4`, `account_code`, `account_name`, `confidence`, `rationale`, `status` — is left exactly as it was. Such a line SHALL be reported as **stale**.

A stale line SHALL NOT be returned to `uncategorized`, SHALL NOT be requeued for AI categorization, and SHALL NOT lose a human verification. The clearing SHALL record an `AuditLog` row on the line with actor `system`.

#### Scenario: Stale lines keep their decision

- **WHEN** a company's tree is changed and a `verified` line's node is not in the new tree
- **THEN** the line stays `verified` with its levels intact, its `spend_category_id` is null, it is reported stale, and an audit row records the change

#### Scenario: Staleness clears when the line is re-verified

- **WHEN** a manager verifies a stale line choosing a node in the company's current tree
- **THEN** the line's `spend_category_id` is set, its levels are taken from that node, and it is no longer stale

## MODIFIED Requirements

### Requirement: AI categorization writes the result onto the line

AI categorization SHALL write the result directly onto the `InvoiceLine` — `level_1`, `level_2`, `level_3`, `level_4`, `account_code`, `account_name`, `confidence`, `rationale`, and the resolved `spend_category_id` when it maps to a node of the company's **assigned** spend tree — and SHALL record an `AuditLog` entry attributed to `system`. There is no separate domain categorization row.

The candidate set the AI chooses from SHALL be the nodes of the company's assigned tree. When the company's tree is four levels deep, the result MAY name a depth-4 node and `level_4` SHALL then be set; on a three-level tree `level_4` SHALL remain null.

#### Scenario: Result is readable on the line

- **WHEN** a line has been AI-categorized
- **THEN** its category, confidence, and rationale are readable directly from the line

#### Scenario: The candidate set is the assigned tree

- **WHEN** two companies in one organization are assigned different trees
- **THEN** each company's lines are categorized only against its own tree's nodes

#### Scenario: A four-level match records its leaf

- **WHEN** the AI matches a depth-4 node
- **THEN** the line's `level_4` holds that node's name and `spend_category_id` names that node

### Requirement: Human verification

The API SHALL let an authorized user (management role) verify an invoice line, optionally correcting its category fields, which sets the line's status to `verified` and records an `AuditLog` entry attributed to that user. Verification of a corrected line SHALL persist the corrected values as the line's categorization.

A correction MAY be expressed as a `spend_category_id` naming a node of the company's assigned tree, in which case the line's `level_1`..`level_4` SHALL be taken from that node's path rather than from the caller — so a corrected line always resolves to a real node. A `spend_category_id` outside the company's assigned tree SHALL be rejected with `422 Unprocessable Entity`.

#### Scenario: Verify accepts the AI result

- **WHEN** a manager verifies an `ai_categorized` line without changes
- **THEN** the line's status becomes `verified` and an audit entry records the verification

#### Scenario: Verify with correction

- **WHEN** a manager verifies a line while changing its category
- **THEN** the corrected values are saved, status becomes `verified`, and the audit entry records the field changes

#### Scenario: Choosing a node sets the levels

- **WHEN** a manager verifies a line supplying only a `spend_category_id`
- **THEN** the line's `level_1`..`level_4` are set from that node's path and the audit entry records each changed level

#### Scenario: Non-manager cannot verify

- **WHEN** a `member` or `viewer` attempts to verify a line
- **THEN** the API responds `403 Forbidden` and the line is unchanged
