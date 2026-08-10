## ADDED Requirements

### Requirement: Spend trees are managed in Settings

Settings SHALL carry a **Spend trees** section, reachable at `/settings/spend-trees` and linked from the settings navigation like the other sections. It SHALL list the organization's trees, each showing its name, depth (`3 levels` / `4 levels`), whether it is the default-template copy or a custom tree, its node count, and the companies assigned to it.

The section SHALL be readable by any authenticated member and SHALL gate every mutating control behind the management role, using the same disabled-with-explanation treatment the rest of Settings uses.

#### Scenario: The organization's trees are listed

- **WHEN** a member opens `/settings/spend-trees`
- **THEN** each of the organization's trees is listed with its depth, source, node count, and assigned companies

#### Scenario: A viewer sees but cannot change

- **WHEN** a `viewer` opens the section
- **THEN** the trees are readable and every create, edit, import, and assign control is unavailable with the reason shown

#### Scenario: The default tree is obtainable from the section

- **WHEN** the organization holds no default-template tree
- **THEN** the section offers to add it, and taking that offer creates the organization's copy and lists it

#### Scenario: The offer disappears once taken

- **WHEN** the organization already holds a default-template copy
- **THEN** the section does not offer to add one

#### Scenario: Loading, empty, and error states

- **WHEN** the tree list is loading, returns nothing, or fails
- **THEN** the section shows the loading, empty, or error state rather than an ambiguous blank panel

### Requirement: A tree can be archived or deleted from its row

Each tree row SHALL offer, to a manager only, **Archive** and **Delete**. Deleting SHALL confirm first, and SHALL surface the server's refusal rather than a generic failure: a tree still assigned to a company names those companies and is not retryable by confirming, while a tree that categorized lines point at reports the count and SHALL be retryable with an explicit "delete anyway".

#### Scenario: Deleting an unused tree

- **WHEN** a manager deletes a tree nothing uses and confirms
- **THEN** the tree is removed from the list

#### Scenario: A tree in use explains itself

- **WHEN** the delete is refused because a company is assigned
- **THEN** the dialog names the companies and offers no way to force it

#### Scenario: Orphaning lines is a decision, not a wall

- **WHEN** the delete is refused because three lines are categorized against the tree
- **THEN** the dialog reports the three lines and offers to delete anyway, which succeeds

#### Scenario: A read-only member gets no row actions

- **WHEN** a `member` or `viewer` views the list
- **THEN** no archive or delete control is offered

### Requirement: A tree is created by cloning, from scratch, or by CSV import

The create flow SHALL offer three starting points in one dialog: **clone an existing tree**, **start empty**, and **import a CSV**. Cloning SHALL default to the organization's default-template copy. The dialog SHALL let the caller name the tree and choose a maximum depth of 3 or 4, with 4 unavailable when cloning the default-template copy is not the chosen path only insofar as the server rejects it — the client SHALL surface the server's reason rather than inventing its own rule.

CSV import SHALL show the file's parsed row count before applying, and on rejection SHALL show the offending rows with their line numbers rather than a single opaque failure. A rejected import SHALL leave the tree visibly unchanged.

#### Scenario: Cloning the default

- **WHEN** a manager creates a tree choosing "clone" with the default-template copy as the source
- **THEN** a new custom tree appears in the list with the same node count, and editing it does not change the source tree

#### Scenario: Import errors are actionable

- **WHEN** an imported CSV has three invalid rows
- **THEN** the dialog names each offending row with its line number and reason, and the tree's node count is unchanged

#### Scenario: A replace import warns first

- **WHEN** a replace import would remove nodes that categorized lines reference
- **THEN** the dialog reports how many lines are affected and requires an explicit confirmation before applying

### Requirement: A tree's nodes are edited as a tree

Opening a tree SHALL show its nodes as an expandable hierarchy, not a flat table of level columns. A manager SHALL be able to add a child under any node, rename a node, reorder siblings, edit a node's description and code, and delete a node.

The editor SHALL make depth legible: adding a child under a node already at the tree's maximum depth SHALL be unavailable, with the reason stated, rather than offered and then rejected by the server. Deleting a node with children SHALL be refused with its child count shown. Deleting a node that categorized lines reference SHALL state how many lines will lose their category pointer before it is confirmed.

#### Scenario: Adding a child

- **WHEN** a manager adds a child under a level-2 node of a 4-level tree
- **THEN** the node appears at level 3 under that parent and the tree's node count increases by one

#### Scenario: Depth limit is visible before it bites

- **WHEN** a manager views a node at the tree's maximum depth
- **THEN** the add-child control is unavailable and states that the tree's maximum depth has been reached

#### Scenario: Deleting a referenced node is confirmed

- **WHEN** a manager deletes a node that 12 invoice lines reference
- **THEN** the confirmation states that 12 lines will lose their category assignment, and cancelling changes nothing

### Requirement: A company's tree is chosen in company settings

Company settings SHALL let a manager choose which spend tree the company categorizes against, from the organization's active trees. When the organization holds no default-template copy, the picker SHALL additionally offer the default — choosing it creates and assigns the copy — because a company that predates spend trees has no tree and creating a new company is not a reasonable way to obtain one. The option SHALL disappear once the copy exists, where it would duplicate the entry already listed by name. The current tree SHALL be shown wherever the company's other categorization-relevant settings are shown.

Changing the assignment SHALL warn before saving that already-categorized lines whose category is not in the new tree will be marked for review, and SHALL make clear that no categorization values are deleted. After saving, the outcome SHALL be reported with the exact number of affected lines and a link to them.

The count is stated **after** the save, not before it: it exists only server-side, and there is no dry-run endpoint. Reporting the exact number the moment it is known is preferable to estimating it beforehand — a wrong number in a confirmation is worse than no number.

#### Scenario: Choosing a different tree

- **WHEN** a manager changes a company's spend tree
- **THEN** the form states that lines whose category is not in the new tree will need reviewing, and that their existing categories are kept

#### Scenario: The outcome is reachable

- **WHEN** the reassignment completes
- **THEN** the result reports the affected line count and links to the entries view filtered to those lines

#### Scenario: Only the organization's trees are offered

- **WHEN** the tree picker opens
- **THEN** it lists only the caller's organization's active trees
