# frontend-line-paging Specification

## Purpose

An invoice's lines are reviewed one at a time in the voucher detail panel, not
stacked down it. This capability covers the paged line card and everything that
follows from showing one line rather than all of them: the Previous/Next
navigation and its position indicator, the keyboard model, the motion that tells
the reviewer which way they moved, and the behaviour at the first and last line,
on an invoice with no lines at all, and while an edit is unsaved.

The paged card is what makes a line's fields editable at a usable size — a stack
of expanded cards is unreadable on a side panel — and it is why paging must never
lose a reviewer's work or leave them unsure how much invoice is left.

## Requirements

### Requirement: An invoice's lines are reviewed one at a time

The voucher panel's Lines tab SHALL render exactly one invoice line at a time,
with Previous and Next controls and a position indicator, rather than stacking
every line down the panel.

- Exactly one line SHALL be in the DOM as an editable card. Rendering the others
  hidden would keep their inputs focusable and their unsaved state alive.
- The indicator SHALL state both the position and the count (`4 of 6`), so a
  reviewer knows how much invoice is left without stepping through it.
- Order SHALL be the line's `sequence`, with `id` as the tiebreak — the order its
  source stated, which is the order it appears on the document.
- The tab SHALL open on the invoice's first line.

#### Scenario: One line is rendered

- **WHEN** the Lines tab opens on an invoice with six lines
- **THEN** one line card is rendered, the indicator reads `1 of 6`, and no input
  belonging to any other line exists in the document

#### Scenario: Next advances one line

- **WHEN** the reviewer activates Next on line 1 of 6
- **THEN** line 2 is rendered and the indicator reads `2 of 6`

#### Scenario: Lines are ordered as the document stated them

- **WHEN** an invoice's lines are returned with sequences 2, 0, 1
- **THEN** stepping from the first line visits them in sequence order 0, 1, 2

### Requirement: Paging stops at the ends rather than wrapping

Previous on the first line and Next on the last SHALL be disabled, not wrapped.

Wrapping from the last line to the first is indistinguishable from having made no
progress, and a reviewer working down a long invoice cannot tell whether they
have finished it.

#### Scenario: The first line cannot go back

- **WHEN** the first line is shown
- **THEN** Previous is disabled and Next is enabled

#### Scenario: The last line cannot go forward

- **WHEN** the last line is shown
- **THEN** Next is disabled and Previous is enabled

#### Scenario: A single line offers no navigation

- **WHEN** the invoice has exactly one line
- **THEN** both controls are disabled and the indicator reads `1 of 1`

### Requirement: Lines are navigable from the keyboard

The paged card SHALL be operable without a mouse.

- Previous and Next SHALL be real buttons, reachable by Tab and activated by
  Enter or Space.
- Left and Right arrow keys SHALL step between lines **only** while focus is
  outside a text-entry control, so an arrow key inside a field still moves the
  caret.
- The control set SHALL carry an accessible name stating what it pages
  (`Previous line` / `Next line`), never a bare chevron.

#### Scenario: Arrow keys page when focus is not in a field

- **WHEN** focus is on the card container and the Right arrow is pressed
- **THEN** the next line is shown

#### Scenario: Arrow keys move the caret inside a field

- **WHEN** focus is inside the item-name input and the Right arrow is pressed
- **THEN** the caret moves within the text and the shown line does not change

#### Scenario: Navigation controls are named

- **WHEN** the navigation controls are rendered
- **THEN** each has an accessible name identifying it as line navigation

### Requirement: Paging away from unsaved edits does not discard them silently

Paging away from a line with unsaved edits SHALL NOT discard them silently. A
line card holds pending changes until they are saved, and stepping to the next
line must not throw that work away without the reviewer knowing.

- When the shown line has unsaved edits, activating Previous or Next SHALL
  prompt for confirmation before leaving.
- Confirming SHALL discard the edits and page; declining SHALL stay on the line
  with the edits intact.
- A line with no pending edits SHALL page immediately, with no prompt — a
  confirmation on every step would make the ordinary case unusable.

#### Scenario: Leaving a dirty line asks first

- **WHEN** the reviewer changes an amount and activates Next
- **THEN** a confirmation is shown and the line has not changed

#### Scenario: Declining keeps the edit

- **WHEN** the reviewer declines that confirmation
- **THEN** the same line is still shown with the changed amount still in its
  input

#### Scenario: A clean line pages immediately

- **WHEN** the reviewer activates Next without having edited anything
- **THEN** the next line is shown with no prompt

### Requirement: The card transition states the direction of travel

Moving between lines SHALL be animated directionally — a Next entering from the
trailing edge, a Previous from the leading edge — so the motion carries which way
the reviewer moved rather than being decoration.

- Only compositor-safe properties SHALL be animated: `transform`, `opacity`,
  `clip-path`. Never `width`, `height`, `top`, or `left`.
- The transition SHALL be under 250ms. This is a data-entry surface, and motion a
  reviewer has to wait through is a cost paid on every line of every invoice.
- Under `prefers-reduced-motion: reduce` the transition SHALL be suppressed
  entirely and the new line SHALL appear immediately.
- No animation SHALL loop, drift, or run while the reviewer is idle.

#### Scenario: Direction is encoded

- **WHEN** the reviewer activates Next and then Previous
- **THEN** the entering card travels from opposite edges for the two actions

#### Scenario: Reduced motion is honoured

- **WHEN** the viewer has `prefers-reduced-motion: reduce` set and pages a line
- **THEN** the new line is shown with no transition

#### Scenario: Nothing animates at rest

- **WHEN** the card has been idle since its transition finished
- **THEN** no animation or transition is running on it

### Requirement: The empty case is stated, not paged

An invoice with no lines SHALL show its existing empty state, with no navigation
controls and no position indicator.

#### Scenario: No lines to page

- **WHEN** the Lines tab opens on an invoice with no lines
- **THEN** the empty state is shown and no Previous, Next, or indicator is
  rendered
