## ADDED Requirements

### Requirement: A line's category is chosen from the tree, not typed

In the voucher slide-over, correcting a line's categorization SHALL be a **tree selector** over the company's assigned spend tree, replacing the free-text level inputs. The reviewer SHALL pick a node; the levels SHALL be derived from that node's path and shown as read-back text, never as separately editable strings.

Free text cannot be right here: a typed level that matches no node produces a categorization resolving to nothing, which is exactly the silent failure the stored `spend_category_id` exists to prevent.

The selector SHALL:

- present the tree level by level, so the reviewer sees where in the taxonomy they are,
- offer a search across all node paths, so a known leaf is reachable without drilling,
- show the full path of the chosen node before saving,
- support trees of three and four levels without a layout change,
- allow choosing a non-leaf node when the tree's own shape permits it, since a three-level tree's level-2 node is a legitimate answer.

#### Scenario: Picking a node sets the whole path

- **WHEN** a reviewer selects `Indirect > Technology > Cloud Infrastructure`
- **THEN** all three levels are shown as the chosen path and the save sends that node's id

#### Scenario: Search reaches a deep leaf

- **WHEN** a reviewer types part of a level-4 node's name
- **THEN** matching nodes are listed with their full paths and selecting one sets the path

#### Scenario: Four levels need no different screen

- **WHEN** the company's tree has four levels
- **THEN** the selector presents the fourth level in the same control, with no separate input appearing

#### Scenario: Levels are not free text

- **WHEN** the category editor is open
- **THEN** there is no editable text input for `level_1`, `level_2`, `level_3`, or `level_4`

### Requirement: A category that no longer resolves is shown as needing review

A line whose stored categorization no longer resolves to a node in its company's assigned tree SHALL be marked in the entries view and in the slide-over as needing review, showing the stored path as the previous decision rather than as the current category.

The stored levels SHALL remain visible — they are the record of what was decided, and hiding them would destroy the reviewer's only clue about what the line was. The marking SHALL be distinguishable from `ai_failed`: nothing failed, the taxonomy moved.

#### Scenario: A stale line is marked

- **WHEN** a line's category does not resolve in the company's assigned tree
- **THEN** the line is marked as needing review and its stored path is presented as the previous category

#### Scenario: Re-picking clears the mark

- **WHEN** a reviewer selects a node from the current tree and saves
- **THEN** the line is no longer marked and shows the new path as its category

#### Scenario: Stale is not failure

- **WHEN** stale lines and `ai_failed` lines are both present
- **THEN** they are visually and textually distinct

### Requirement: The category editor degrades honestly when there is no tree

When a line's company has no assigned spend tree, the category editor SHALL say so and SHALL NOT offer a selector over an empty set or fall back to free-text inputs. It SHALL point a manager at where the tree is chosen.

#### Scenario: No tree, no selector

- **WHEN** the line's company has no assigned spend tree
- **THEN** the editor states that no spend tree is assigned and links to company settings instead of showing an empty picker

#### Scenario: The rest of the line still reads

- **WHEN** no tree is assigned
- **THEN** the line's description, amount, status, and rationale remain visible as evidence
