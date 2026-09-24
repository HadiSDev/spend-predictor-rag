# spend-tree-gap-suggestions Specification

## Purpose
TBD - created by archiving change spend-categorizer-overhaul. Update Purpose after archive.
## Requirements
### Requirement: The platform SHALL propose categories a company's tree is missing, evidenced by its own spend

A suggester SHALL read a company's categorized lines together with its assigned spend tree and propose nodes the tree does not have but the spend calls for. Each suggestion SHALL name a **parent** it would hang under, a proposed name and description, and **the lines that evidence it**.

This exists because the alternative is invisible. A tree with no home for rail travel does not announce itself: it produces a stream of confidently-mistaken or barely-confident categorizations, spread across months, that nobody reads as a taxonomy problem. The evidence lines are the whole point — a proposal a reviewer cannot check is a proposal they cannot accept.

#### Scenario: A missing category is proposed with its evidence

- **WHEN** a company's tree has no ground-transport node and eleven lines from rail and taxi suppliers were categorized elsewhere with low confidence
- **THEN** a suggestion proposes a ground-transport node under the travel parent and lists those lines as its evidence

#### Scenario: A category the tree already has is not proposed

- **WHEN** the tree already holds a node covering the spend in question
- **THEN** no suggestion is produced for it

#### Scenario: A suggestion names where it would go

- **WHEN** a suggestion is produced
- **THEN** it names an existing node of that company's tree as the parent it would be added under

### Requirement: Low-confidence categorizations SHALL be the suggester's primary signal

The suggester SHALL weigh lines the categorizer answered with low confidence more heavily than lines it answered confidently. A confident answer is evidence the tree works; a run of unconfident answers over similar spend is evidence it does not.

The suggester SHALL NOT treat a single low-confidence line as a gap. A category is a structural claim about a company's spending, and one odd purchase is not one.

#### Scenario: A run of unconfident answers surfaces a gap

- **WHEN** many lines describing similar spend were categorized with low confidence
- **THEN** they are grouped and proposed as one gap rather than as many

#### Scenario: One odd line is not a taxonomy change

- **WHEN** a single line was categorized with low confidence and resembles nothing else
- **THEN** no suggestion is produced from it

### Requirement: A suggestion SHALL be a proposal a human accepts or dismisses, and SHALL never write a node unattended

No suggestion SHALL create, rename, move or delete a `SpendCategory`. A suggestion SHALL be stored as its own record with a state of pending, accepted, or dismissed, and SHALL become a tree node only through the existing node-creation path, invoked by a person with management rights.

A tree is the customer's statement of how they think about their own spending. A system that edits it while they sleep has taken that away, and every categorization made against the edited tree afterwards is against a taxonomy they never chose.

#### Scenario: Accepting a suggestion creates the node through the normal path

- **WHEN** a manager accepts a suggestion
- **THEN** the node is created under the named parent by the same service that creates any node, and the suggestion is marked accepted

#### Scenario: A dismissed suggestion is not proposed again

- **WHEN** a manager dismisses a suggestion and the suggester runs again over the same spend
- **THEN** the dismissed suggestion is not re-proposed

#### Scenario: Running the suggester changes no tree

- **WHEN** the suggester runs against a company with many gaps
- **THEN** the company's tree is byte-for-byte unchanged and only suggestion records are written

#### Scenario: A read-only role may see but not accept

- **WHEN** a `viewer` opens the suggestions for a tree
- **THEN** the suggestions are readable and no accept or dismiss action is available to them

### Requirement: A suggestion SHALL be scoped to one organization's tree and SHALL expire against a changed one

A suggestion SHALL name the tree it was produced for, and SHALL be visible only to that tree's organization. A suggestion whose proposed parent no longer exists SHALL NOT be offered for acceptance.

#### Scenario: Suggestions are tenant-scoped

- **WHEN** an organization lists the suggestions for its tree
- **THEN** no suggestion produced for another organization's tree is returned

#### Scenario: A suggestion orphaned by an edit is not acceptable

- **WHEN** the parent a pending suggestion names is deleted from the tree
- **THEN** that suggestion can no longer be accepted

