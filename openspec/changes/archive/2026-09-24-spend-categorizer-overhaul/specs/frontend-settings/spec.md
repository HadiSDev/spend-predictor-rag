## ADDED Requirements

### Requirement: A tree's suggested categories SHALL be reviewable where the tree is edited

The spend-tree editor in Settings SHALL surface the pending gap suggestions for the tree being edited, each showing the proposed name, the parent it would be added under, the reason given, and the lines that evidence it.

They belong beside the tree rather than in a notifications area because accepting one is a tree edit: the reviewer needs the tree in front of them to judge whether the proposal duplicates a node they already have, and to see where it would land.

#### Scenario: Suggestions appear with the tree

- **WHEN** a manager opens a tree that has pending suggestions
- **THEN** the suggestions are visible alongside its nodes, each naming its proposed parent

#### Scenario: The evidence is reachable

- **WHEN** a manager opens a suggestion
- **THEN** the lines that evidence it are listed and each links to that line

#### Scenario: A tree with no suggestions shows no empty apparatus

- **WHEN** a tree has no pending suggestions
- **THEN** the editor shows the tree as it does today, with no empty suggestions panel

### Requirement: Accepting a suggestion SHALL show its result in the tree, and dismissing SHALL be undoable in the same session

Accepting a suggestion SHALL create the node and show it in the tree immediately, in the position it was proposed for, so the reviewer sees the consequence where they caused it. Dismissing SHALL remove the suggestion from the list and SHALL offer an undo for the remainder of that session.

Accept and dismiss SHALL be available only to a role that may edit the tree. A read-only role SHALL see the suggestions as evidence and SHALL NOT be shown disabled accept controls, which claim a permission that will never be granted.

#### Scenario: An accepted suggestion becomes a visible node

- **WHEN** a manager accepts a suggestion
- **THEN** the new node appears under the named parent in the tree without a reload

#### Scenario: A dismissal can be taken back

- **WHEN** a manager dismisses a suggestion
- **THEN** an undo is offered and taking it restores the suggestion to the pending list

#### Scenario: A viewer sees evidence, not controls

- **WHEN** a `viewer` opens a tree with pending suggestions
- **THEN** the suggestions and their evidence are readable and no accept or dismiss control is rendered
