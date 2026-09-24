# spend-tree-management Specification

## Purpose

Define how a customer organization owns, authors, and assigns the spend taxonomy its companies are categorized against: an org-owned `SpendTree` of `SpendCategory` nodes, a platform default template copied into the org on first use, three authoring paths (clone, empty, CSV import), the API that reads and manages trees and nodes, and the rule that reassigning a company's tree never rewrites or discards an existing categorization — it only clears the pointer and marks the line stale.
## Requirements
### Requirement: A spend tree is owned by the organization and assigned to companies

A `SpendTree` SHALL be a named taxonomy belonging to an `Organization` (`organization_id` FK → organizations), carrying a `name`, a `max_depth` of 3 or 4, a `source` of `default_template` | `custom`, an optional `template_version` recording which platform template it was copied from, and a soft-archive flag. Each `Company` SHALL carry a nullable `spend_tree_id` naming the tree it categorizes against; the tree MUST belong to the same organization as the company.

Several companies MAY share one tree, and one organization MAY hold several trees. A tree SHALL NOT be assigned to a company in another organization.

#### Scenario: One tree serves several companies

- **WHEN** two companies in the same organization are both assigned tree `T`
- **THEN** both categorize against `T`'s nodes and neither holds a private copy

#### Scenario: A tree cannot cross organizations

- **WHEN** a caller assigns a tree belonging to organization `A` to a company in organization `B`
- **THEN** the API responds `404 Not Found` and the company's assignment is unchanged

#### Scenario: An unassigned company falls back to the org default

- **WHEN** a company has no `spend_tree_id`
- **THEN** it categorizes against the organization's default-template tree, which is created on first use

### Requirement: The default spend tree is a platform template copied into the organization

The platform SHALL ship a versioned default spend-tree template, three levels deep, whose `level_1` values are exactly `Direct` and `Indirect`. The template SHALL be the single definition of the built-in taxonomy — the categorizer's former hard-coded table SHALL be derived from it, not maintained separately.

The template SHALL be **copied** into an organization the first time that organization needs it, producing a `SpendTree` with `source = default_template`, `max_depth = 3`, and the `template_version` it was copied from. The copy SHALL be editable by the organization, and editing it SHALL NOT affect the template or any other organization's copy. An organization SHALL hold at most one default-template copy; a request that would create a second SHALL return the existing one.

#### Scenario: First use materializes the copy

- **WHEN** an organization's first company is created and no tree is named
- **THEN** a `SpendTree` with `source = default_template` and `max_depth = 3` is created for that organization from the template, its nodes are seeded, and the company is assigned to it

#### Scenario: Editing a copy is tenant-local

- **WHEN** organization `A` renames a node in its default-template copy
- **THEN** organization `B`'s copy and the shipped template are unchanged

#### Scenario: The default template's level 1 is closed

- **WHEN** the default template is seeded
- **THEN** every node's `level_1` is either `Direct` or `Indirect`, and no node is deeper than level 3

#### Scenario: Copying is idempotent per organization

- **WHEN** the default-template copy is requested twice for the same organization
- **THEN** the second request returns the existing tree and creates no second copy

### Requirement: The default tree can be obtained without creating a company

The API SHALL provide `POST /api/v1/spend-trees/default`, which returns the organization's copy of the platform template, creating and seeding it when absent. It SHALL be idempotent and SHALL respond `200 OK` rather than `201`, since the usual answer is the copy that already exists. It SHALL require the management role.

This exists because copy-on-first-use otherwise has exactly **one** trigger — creating a company — which leaves an organization whose companies predate spend trees with no way to obtain the default at all.

#### Scenario: An organization with no companies to create gets the default

- **WHEN** a manager of an organization holding no default-template tree posts to `/api/v1/spend-trees/default`
- **THEN** the organization's copy is created and seeded from the template and returned with its nodes

#### Scenario: Asking twice changes nothing

- **WHEN** the endpoint is called a second time
- **THEN** it returns the same tree and the organization still holds exactly one template copy

#### Scenario: A read-only member cannot materialize it

- **WHEN** a `member` or `viewer` posts to `/api/v1/spend-trees/default`
- **THEN** the API responds `403 Forbidden` and no tree is created

### Requirement: Custom trees may go four levels deep; the default stays at three

A tree SHALL declare a `max_depth`. A `default_template` tree SHALL have `max_depth = 3`. A `custom` tree MAY declare `max_depth` of 3 or 4. A node SHALL NOT be written at a depth greater than its tree's `max_depth`; such a write SHALL be rejected with `422 Unprocessable Entity` rather than truncated or silently accepted.

Raising a tree's `max_depth` from 3 to 4 SHALL be permitted. Lowering it SHALL be rejected while any node exists below the proposed maximum.

#### Scenario: A fourth level on a custom tree is accepted

- **WHEN** a node is added under a level-3 node of a custom tree with `max_depth = 4`
- **THEN** the node is created at depth 4 and its `level_4` is set

#### Scenario: A fourth level on the default copy is rejected

- **WHEN** a node is added at depth 4 to a tree with `max_depth = 3`
- **THEN** the API responds `422 Unprocessable Entity` and no node is created

#### Scenario: Lowering max_depth with deep nodes present is rejected

- **WHEN** a tree with `max_depth = 4` holding depth-4 nodes is updated to `max_depth = 3`
- **THEN** the API responds `422 Unprocessable Entity` and the tree is unchanged

### Requirement: A tree node is a real tree node, not four loose columns

A `SpendCategory` SHALL carry `spend_tree_id`, a nullable `parent_id` (FK → spend_categories, null at depth 1), a `depth` of 1–4, a `name` (the node's own label), a `sort_order`, an optional `code`, and an optional `description`. Its `level_1`..`level_4` columns SHALL be the **materialized path** — the names of its ancestors and itself — kept in step with `parent_id` on every write, so a categorization result can be read without walking the tree.

Sibling names SHALL be unique under one parent within a tree. `code`, when present, SHALL be unique within a tree.

#### Scenario: The path is materialized on insert

- **WHEN** a node named `Compute` is created under `Indirect > Technology > Cloud Infrastructure`
- **THEN** it is stored with `depth = 4`, that parent, and `level_1..level_4` = `Indirect`, `Technology`, `Cloud Infrastructure`, `Compute`

#### Scenario: Renaming a node rewrites its descendants' path

- **WHEN** a level-2 node is renamed
- **THEN** every descendant's materialized `level_*` path is rewritten in the same transaction

#### Scenario: Duplicate siblings are rejected

- **WHEN** a node is created with a name that already exists under the same parent in the same tree
- **THEN** the API responds `409 Conflict` and no node is created

### Requirement: Trees are authored by cloning, by hand, or by CSV import

The API SHALL support three ways to produce a tree, all resulting in the same node rows:

- **Clone** — `POST /api/v1/spend-trees` with `source_tree_id` copies an existing tree's nodes into a new `custom` tree in the caller's organization.
- **From scratch** — `POST /api/v1/spend-trees` with no source creates an empty `custom` tree whose nodes are then added one at a time.
- **CSV import** — `POST /api/v1/spend-trees/{id}/import` accepts a CSV with columns `level_1`, `level_2`, `level_3`, `level_4`, `description`, and optionally `code`.

An import SHALL be validated in full before anything is written and SHALL be applied **wholly or not at all**: a file with any invalid row SHALL be rejected with a per-row error report and SHALL leave the tree exactly as it was. A row deeper than the tree's `max_depth`, a row with a gap in its path (a `level_3` with no `level_2`), and a duplicate sibling path SHALL each be invalid.

An import SHALL declare whether it `replaces` the tree's nodes or `merges` into them. A replace SHALL be refused while any `InvoiceLine` references a node it would remove, unless the caller confirms; a refusal SHALL name the affected node count.

All three SHALL require the management role.

#### Scenario: Clone produces an independent tree

- **WHEN** a manager clones the organization's default-template copy
- **THEN** a new `custom` tree is created with the same node structure, and editing either tree leaves the other unchanged

#### Scenario: A malformed CSV changes nothing

- **WHEN** an import file has 200 valid rows and one row with a `level_3` but no `level_2`
- **THEN** the API responds `422 Unprocessable Entity` naming the offending row, and the tree's nodes are unchanged

#### Scenario: An over-deep CSV row is rejected

- **WHEN** an import into a `max_depth = 3` tree contains a row with a `level_4` value
- **THEN** the whole import is rejected and no node is written

#### Scenario: Replace warns before orphaning categorized lines

- **WHEN** a replace import would remove nodes referenced by 42 invoice lines and the caller has not confirmed
- **THEN** the API responds `409 Conflict` reporting 42 affected lines, and nothing is written

#### Scenario: Import requires management

- **WHEN** a `member` or `viewer` posts an import
- **THEN** the API responds `403 Forbidden` and nothing is written

### Requirement: Trees and nodes are readable and manageable through the API

The API SHALL expose:

- `GET /api/v1/spend-trees` — the organization's trees, each with its node count, `max_depth`, `source`, and the companies assigned to it.
- `GET /api/v1/spend-trees/{id}` — one tree with its nodes, ordered by `depth` then `sort_order` then `name`, in a shape a client can render as a tree without a second request.
- `POST /api/v1/spend-trees`, `PATCH /api/v1/spend-trees/{id}`, `POST /api/v1/spend-trees/{id}/archive`.
- `POST /api/v1/spend-trees/{id}/nodes`, `PATCH /api/v1/spend-tree-nodes/{id}`, `DELETE /api/v1/spend-tree-nodes/{id}`.

Reads SHALL be available to any authenticated member of the organization; writes SHALL require the management role. Every endpoint SHALL be tenant-scoped: a tree outside the caller's organization SHALL respond `404 Not Found`.

A tree MAY be **archived** (retired from the pickers, history reachable) or **deleted** outright via `DELETE /api/v1/spend-trees/{id}`. Neither is possible while a company is assigned to it — a company whose tree id dangles categorizes nothing, so the companies are reassigned first.

Deletion is hard, unlike a `Company`'s soft deactivation, because a tree owns no financial record: an `InvoiceLine` keeps its `level_1..level_4` whatever happens to the node it pointed at. A delete that would orphan categorized lines SHALL be refused with `409 Conflict` and the affected count until the caller passes `confirm=true`; on confirm those lines' `spend_category_id` is cleared, their stored levels and status are untouched, and they become stale. Deleting a node with children SHALL be rejected; deleting a node referenced by invoice lines SHALL clear those lines' `spend_category_id` and leave their stored `level_*` values in place.

#### Scenario: Reading a tree returns a renderable structure

- **WHEN** a member GETs a tree
- **THEN** the response carries every node with its `id`, `parent_id`, `depth`, `name`, and `sort_order`, ordered so a client can build the hierarchy in one pass

#### Scenario: A member cannot edit

- **WHEN** a `viewer` PATCHes a node
- **THEN** the API responds `403 Forbidden` and the node is unchanged

#### Scenario: An assigned tree cannot be archived

- **WHEN** a manager archives a tree that a company is assigned to
- **THEN** the API responds `409 Conflict` naming the companies, and the tree stays active

#### Scenario: An unused tree is deleted outright

- **WHEN** a manager deletes a tree that no company is assigned and no line is categorized against
- **THEN** the tree and every one of its nodes are removed

#### Scenario: An assigned tree cannot be deleted

- **WHEN** a manager deletes a tree a company is assigned to
- **THEN** the API responds `409 Conflict` naming the companies and deletes nothing

#### Scenario: Deleting a tree lines use is confirmed, not refused

- **WHEN** a manager deletes a tree whose nodes three invoice lines point at, without confirming
- **THEN** the API responds `409 Conflict` reporting three lines and deletes nothing; and on a second request with `confirm=true` the tree is deleted, those lines keep every stored level and status, and their `spend_category_id` is cleared

#### Scenario: Deleting a node with children is refused

- **WHEN** a manager deletes a node that has descendants
- **THEN** the API responds `409 Conflict` and no node is deleted

#### Scenario: Another organization's tree is invisible

- **WHEN** a caller GETs a tree id belonging to another organization
- **THEN** the API responds `404 Not Found`

### Requirement: Reassigning a company's tree keeps history and marks it stale

Changing a `Company.spend_tree_id` SHALL NOT rewrite, requeue, or delete any existing categorization. For every `InvoiceLine` of that company whose `spend_category_id` points at a node **not** in the newly assigned tree, the change SHALL, in the same transaction:

- clear `spend_category_id`,
- leave `level_1`..`level_4`, `account_code`, `account_name`, `confidence`, `rationale` and `status` exactly as they were,
- and record an `AuditLog` row on the line with action `spend_tree_reassigned`, actor `system`, carrying the previous `spend_category_id` and both tree ids.

A line in that state SHALL be identifiable as **stale** — its stored category no longer resolves to a node in the tree the company now uses — so a reviewer can see what needs re-deciding without any value having been silently changed.

A line whose stored path matches a node in the new tree by name at every level MAY be re-resolved to that node instead of cleared; matching SHALL be exact and case-sensitive, never fuzzy.

#### Scenario: Reassignment clears the pointer, not the values

- **WHEN** a company is moved from tree `A` to tree `B` and a verified line pointed at a node in `A` that has no name-equal counterpart in `B`
- **THEN** the line keeps its `level_*` values, its `verified` status, and its rationale; its `spend_category_id` is null; and an audit row records the reassignment

#### Scenario: An identical path re-resolves

- **WHEN** the new tree contains a node whose full name path equals the line's stored `level_*` path
- **THEN** the line's `spend_category_id` is set to that node and the line is not stale

#### Scenario: Staleness is visible

- **WHEN** a client lists invoice lines for a company after a reassignment
- **THEN** lines whose stored category no longer resolves in the assigned tree are flagged stale in the payload

#### Scenario: No verification is lost

- **WHEN** a reassignment affects `verified` lines
- **THEN** none of them return to `uncategorized` and none are requeued for AI categorization

### Requirement: The default template SHALL cover the spend an ordinary company actually books

The shipped template's leaves SHALL cover the categories a small or mid-sized European company books month to month, and SHALL include at minimum a **ground transport** leaf for rail, bus and taxi travel, a **bank and payment fees** leaf, an **insurance** leaf, and a **subscriptions and memberships** leaf, alongside the existing technology, facilities, professional services, marketing, travel, logistics and people branches.

Ground transport is named explicitly because its absence is what produced this requirement: the only travel leaves were airfare, lodging and meals, so a commuter rail ticket had no home in the platform's own default taxonomy and the categorizer was blamed for saying so. Bank fees are named because the categorizer's own documented motivating failure is a bank fee filed under telecom, and the tree it was filed against had no fees leaf either.

#### Scenario: A rail ticket has a home

- **WHEN** a company categorizes a commuter rail ticket against a freshly seeded default tree
- **THEN** the tree offers a ground-transport leaf under its travel branch

#### Scenario: A bank fee has a home

- **WHEN** a company categorizes a card or bank charge against a freshly seeded default tree
- **THEN** the tree offers a fees leaf that is not a technology or telecom node

#### Scenario: The template stays three levels and two roots

- **WHEN** the expanded template is seeded
- **THEN** every node's `level_1` is either `Direct` or `Indirect` and no node is deeper than level 3

### Requirement: A new template version SHALL NOT reach into an organization's existing copy

Raising `TEMPLATE_VERSION` SHALL affect only trees seeded **after** the raise. An organization that already holds a default-template copy SHALL NOT have nodes added to it, removed from it, or renamed within it by a template change.

The copy is the customer's, and it is editable: a node the platform adds might duplicate one they already made, and a node it renames might be one they deliberately renamed first. An organization that wants the newer taxonomy SHALL obtain it the way it obtains any other tree — by creating one — not by having theirs rewritten.

#### Scenario: An existing copy is untouched by a version bump

- **WHEN** the template version is raised and an organization already holds a copy at the previous version
- **THEN** that organization's tree has the same nodes it had before, and its recorded `template_version` is unchanged

#### Scenario: A new organization gets the new template

- **WHEN** an organization first needs a default tree after the version is raised
- **THEN** its copy is seeded from the new template and records the new version

#### Scenario: Categorized lines are unaffected

- **WHEN** the template version is raised
- **THEN** no existing line's `spend_category_id` or `level_1`..`level_4` changes and no line becomes stale

