## ADDED Requirements

### Requirement: SpendTree entity

The domain SHALL carry a `SpendTree` entity, stored in `spend_trees`, holding `id`, `organization_id` (FK → organizations), `name`, `max_depth` (3 or 4), `source` (`default_template` | `custom`), nullable `template_version`, `archived_at`, and `created_at`. The Organization relationship SHALL be exposed as `Organization.spend_trees`.

`Company` SHALL carry a nullable `spend_tree_id` (FK → spend_trees) naming the tree it categorizes against, exposed as `Company.spend_tree`. The referenced tree MUST belong to the company's own organization.

#### Scenario: A tree belongs to an organization, not a company

- **WHEN** an organization's trees are loaded
- **THEN** each is a `SpendTree` row with that `organization_id`, reachable via `Organization.spend_trees`, and companies reference it rather than owning it

#### Scenario: Companies point at a tree

- **WHEN** a company is assigned a tree
- **THEN** `Company.spend_tree_id` holds that tree's id and `Company.spend_tree` resolves to it

### Requirement: InvoiceLine records a fourth categorization level

`InvoiceLine` SHALL carry a nullable `level_4` beside `level_1`, `level_2` and `level_3`, so a categorization against a four-level tree has somewhere to record its leaf. `level_4` SHALL be null whenever the assigned tree is three levels deep, which is the ordinary case, and SHALL NEVER be defaulted or inferred.

`level_4` SHALL be part of the line's auditable categorization fields, so a correction to it is diffed and recorded like any other level.

#### Scenario: A four-level categorization is stored whole

- **WHEN** a line is categorized against a node at depth 4
- **THEN** the line's `level_1`..`level_4` hold that node's full path

#### Scenario: Three-level trees leave it null

- **WHEN** a line is categorized against a three-level tree
- **THEN** the line's `level_4` is null

#### Scenario: Correcting level_4 is audited

- **WHEN** a manager verifies a line while changing its `level_4`
- **THEN** the audit entry records the `level_4` change alongside any other changed field

## MODIFIED Requirements

### Requirement: Spend-tree nodes are modeled as SpendCategory

The spend-tree node SHALL be the `SpendCategory` entity, stored in the `spend_categories` table, replacing the former `Account`/`accounts` naming which collided with the ERP's native `ErpAccount`.

- A `SpendCategory` SHALL belong to a `SpendTree` (`spend_tree_id` FK → spend_trees), **not** to a Company. The former `company_id` column SHALL be removed; a company reaches its nodes through `Company.spend_tree`.
- The tree relationship SHALL be exposed as `SpendTree.categories`.
- A node SHALL carry a nullable `parent_id` (FK → spend_categories, null at depth 1), a `depth` of 1–4, its own `name`, a `sort_order`, an optional `code`, and an optional `description`.
- `name`, `code`, and `description` SHALL be the leaf identity and embedding text used for retrieval and categorization.
- Sibling `name` values SHALL be unique under one parent within a tree, and `code` SHALL be unique within a tree when present.

#### Scenario: Spend categories are scoped to a tree

- **WHEN** a tree's nodes are loaded
- **THEN** each node is a `SpendCategory` row with that `spend_tree_id`, reachable via `SpendTree.categories`, and no node carries a `company_id`

#### Scenario: A company reaches its nodes through its tree

- **WHEN** a company's spend tree is needed
- **THEN** it is resolved as `Company.spend_tree.categories`, and two companies assigned the same tree see the same node rows

#### Scenario: Parentage is explicit

- **WHEN** a node below the top level is loaded
- **THEN** its `parent_id` names its parent node and its `depth` is one greater than that parent's

### Requirement: SpendCategory stores four labelled levels including Direct/Indirect

`SpendCategory` SHALL store an explicit level path `level_1`, `level_2`, `level_3`, `level_4`, where `level_1` holds the Direct/Indirect classification that was previously inferred and never persisted.

- The `level_*` columns SHALL be the **materialized path** of the node — the `name` of each ancestor and of the node itself — derived from `parent_id` and rewritten in the same transaction whenever a node is renamed or reparented. They are a read optimization for categorization results, never an independent source of truth about structure.
- `level_n` SHALL be set exactly when the node's `depth` is at least `n`, and null otherwise. Every `level_*` column is therefore nullable, including `level_2`, which the pre-tree model required: `Direct` and `Indirect` are real depth-1 rows — the tier a reviewer picks first — and a depth-1 node's path is its `level_1` alone.
- `level_1` SHALL hold the Direct/Indirect value on the default template's trees and SHALL be stored on the node. This supersedes the prior rule that L1 is never stored, and the prior rule that `level_2` is required.
- `level_4` SHALL be populated only on a tree whose `max_depth` is 4.

#### Scenario: Direct/Indirect is stored on the node

- **WHEN** a spend category is classified as Direct or Indirect
- **THEN** its `level_1` field holds that value

#### Scenario: A depth-1 node has only its own level

- **WHEN** the node `Indirect` is loaded from the default template's tree
- **THEN** its `depth` is 1, its `level_1` is `Indirect`, and its `level_2`, `level_3` and `level_4` are null

#### Scenario: Optional deeper levels

- **WHEN** a tree uses only two tiers
- **THEN** a leaf has `level_1` and `level_2` set with `level_3` / `level_4` null, and remains valid

#### Scenario: The path follows the structure

- **WHEN** a node's parent is renamed
- **THEN** that node's materialized `level_*` path is rewritten to match, in the same transaction as the rename

### Requirement: InvoiceLine carries its categorization result and status

The `InvoiceLine` domain entity SHALL hold its categorization result directly: `level_1`, `level_2`, `level_3`, `level_4`, `account_code`, `account_name`, `confidence`, `rationale`, plus the accepted `spend_category_id` (FK to a node of the company's assigned spend tree, nullable until resolved). Its `status` SHALL use the categorization vocabulary `uncategorized` | `ai_failed` | `ai_categorized` | `verified`. The line SHALL NOT carry synthetic ground-truth (`gt_*`) fields, and there SHALL be no separate domain `LineCategorization` table.

The stored `level_*` values SHALL survive independently of `spend_category_id`: they are the record of what was decided, and they remain readable when the pointer is cleared because the company's tree changed.

#### Scenario: Result fields on the line

- **WHEN** a line is categorized
- **THEN** its `level_*`, `account_code`, `account_name`, `confidence`, and `rationale` are set on the line and its status reflects `ai_categorized` or `verified`

#### Scenario: No ground truth on the domain line

- **WHEN** inspecting `invoice_lines`
- **THEN** there are no `gt_*` columns

#### Scenario: Levels outlive the pointer

- **WHEN** a line's `spend_category_id` is cleared because its node is not in the company's assigned tree
- **THEN** its `level_1`..`level_4` are unchanged and still readable
