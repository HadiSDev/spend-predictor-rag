## ADDED Requirements

### Requirement: Spend-tree nodes are modeled as SpendCategory

The company spend-tree node SHALL be the `SpendCategory` entity, stored in the `spend_categories` table, replacing the former `Account`/`accounts` naming which collided with the ERP's native `ErpAccount`.

- A `SpendCategory` SHALL belong to a Company (`company_id` FK → companies).
- The Company relationship SHALL be exposed as `Company.spend_categories`.
- `account_code`, `account_name`, and `description` SHALL remain on the node as
  the leaf identity and embedding text used for retrieval and categorization.

#### Scenario: Spend categories are scoped to a company

- **WHEN** a company's spend tree is loaded
- **THEN** each node is a `SpendCategory` row with that `company_id`, reachable via
  `Company.spend_categories`

### Requirement: SpendCategory stores four labelled levels including Direct/Indirect

`SpendCategory` SHALL store an explicit level path `level_1`, `level_2`, `level_3`, `level_4`, where `level_1` holds the Direct/Indirect classification that was previously inferred and never persisted.

- `level_1` SHALL hold the Direct/Indirect value and SHALL be stored on the node
  (nullable when not yet classified). This supersedes the prior rule that L1 is
  never stored.
- `level_2` SHALL be required (the top category).
- `level_3` and `level_4` SHALL be optional (subcategory and deepest tier).
- The former `level2` and `level3` fields SHALL be migrated to `level_2` and
  `level_3` respectively.

#### Scenario: Direct/Indirect is stored on the node

- **WHEN** a spend category is classified as Direct or Indirect
- **THEN** its `level_1` field holds that value

#### Scenario: Optional deeper levels

- **WHEN** a company's tree uses only two labelled tiers
- **THEN** the node has `level_2` set and `level_3` / `level_4` null, and remains
  valid
