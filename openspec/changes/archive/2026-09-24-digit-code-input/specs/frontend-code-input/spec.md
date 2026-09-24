## ADDED Requirements

### Requirement: Segmented one-time-code field

The UI library SHALL export a `CodeInput` from `apps/web/src/components/ui/`
that renders a one-time code as one cell per digit rather than as a single
free-text field. The number of cells SHALL be a `length` prop defaulting to 6,
and the component SHALL be controlled — taking `value` and emitting `onChange`
with the whole code as a string — so it drops into an existing form field
without that form learning anything about cells.

Cells SHALL derive their colors, radius, typography, and focus ring from the
theme tokens the rest of the library uses, so the field reads as part of the
same control set.

#### Scenario: Renders one cell per digit

- **WHEN** `CodeInput` is rendered with `length={6}`
- **THEN** six cells are displayed, each showing at most one character

#### Scenario: Length is configurable

- **WHEN** `CodeInput` is rendered with `length={4}`
- **THEN** four cells are displayed and a four-character value fills them all

#### Scenario: Value is reported as one string

- **WHEN** the user has entered `1`, `2`, and `3` into the first three cells
- **THEN** `onChange` has been called with `"123"`, not with per-cell values

### Requirement: Entry progress is visible

The component SHALL distinguish a filled cell from an empty one, and SHALL mark
the cell awaiting input with the focus ring, so how far through the code the
user is can be read without counting characters. The component SHALL NOT use a
placeholder that renders as a plausible code.

#### Scenario: Filled and empty cells are distinguishable

- **WHEN** three digits of a six-digit code have been entered
- **THEN** the three filled cells are visually distinct from the three empty
  ones

#### Scenario: The active cell is indicated

- **WHEN** the field holds focus with three of six digits entered
- **THEN** the fourth cell carries the focus ring

#### Scenario: No placeholder code is shown

- **WHEN** the field is empty
- **THEN** no cell displays a digit

### Requirement: Digit entry and deletion

Typing a digit SHALL fill the active cell and advance to the next; the last
cell SHALL NOT advance past the end. Characters that are not digits SHALL be
rejected rather than occupying a cell. Backspace SHALL clear the active cell if
it is filled, and otherwise step back to the previous cell and clear that — so
a held Backspace empties the field.

#### Scenario: Typing advances

- **WHEN** the user types `7` into the first cell of an empty field
- **THEN** the first cell shows `7` and the second cell becomes active

#### Scenario: Non-digits are rejected

- **WHEN** the user types `a` into the active cell
- **THEN** no cell changes and the active cell does not advance

#### Scenario: Backspace clears the active cell

- **WHEN** the active cell holds a digit and the user presses Backspace
- **THEN** that cell is cleared and remains active

#### Scenario: Backspace steps back from an empty cell

- **WHEN** the active cell is empty and the user presses Backspace
- **THEN** the previous cell becomes active and is cleared

### Requirement: Paste fills the whole code

Pasting SHALL distribute the pasted text across the cells from the paste
position onward rather than placing it all in one cell. Non-digit characters —
including the spaces mail clients insert when grouping a code — SHALL be
stripped before distribution, and any characters beyond the last cell SHALL be
discarded.

#### Scenario: A full code pastes across the cells

- **WHEN** the user pastes `123456` into an empty six-cell field
- **THEN** the cells read `1 2 3 4 5 6` and `onChange` reports `"123456"`

#### Scenario: A grouped code pastes cleanly

- **WHEN** the user pastes `123 456` into an empty six-cell field
- **THEN** the space is discarded and the cells read `1 2 3 4 5 6`

#### Scenario: Overflow is discarded

- **WHEN** the user pastes `1234567890` into a six-cell field
- **THEN** the first six digits fill the cells and the remainder is discarded

### Requirement: Completion is reported

The component SHALL invoke an optional `onComplete` callback with the full code
at the moment the last empty cell is filled, whether by typing or by pasting,
so a caller can submit without a further click. `onComplete` SHALL fire on the
transition into a complete code and SHALL NOT fire again while the code stays
complete and unchanged, so editing a digit of a complete code does not resubmit
on every keystroke.

Reporting completion SHALL NOT be the only way to submit: the caller's submit
control remains available, since it is the retry path after a rejected code.

#### Scenario: Typing the last digit completes

- **WHEN** the user types the sixth digit of a six-digit code
- **THEN** `onComplete` is called once with the full six-character code

#### Scenario: Pasting a full code completes

- **WHEN** the user pastes a complete code into an empty field
- **THEN** `onComplete` is called once with that code

#### Scenario: An incomplete code does not complete

- **WHEN** the user has entered five digits of a six-digit code
- **THEN** `onComplete` has not been called

#### Scenario: Completion does not repeat

- **WHEN** a complete code is entered and the field is re-rendered without the
  value changing
- **THEN** `onComplete` is not called a second time

### Requirement: Keyboard navigation and focus

The cells SHALL be reachable from the keyboard: focusing the field SHALL place
the entry point at the first empty cell (or the last cell when the code is
complete), and the field SHALL occupy a single Tab stop so tabbing does not walk
through six controls to reach the submit button.

The entry point SHALL always be the end of the entered code — Left and Right
arrows SHALL NOT move it. A code field is positional, and an entry point that
can be moved mid-string makes the next keystroke either insert or overwrite,
either of which silently produces a code the user did not type. A wrong digit is
corrected by Backspace, which is how the platform code fields users already know
behave.

#### Scenario: Focus lands where input is needed

- **WHEN** a field holding three of six digits receives focus
- **THEN** the fourth cell becomes active

#### Scenario: Arrows do not move the entry point

- **WHEN** the field holds three of six digits and the user presses the Left or
  Right arrow
- **THEN** the fourth cell remains active and the code is unchanged

#### Scenario: A wrong digit is corrected by Backspace

- **WHEN** a complete code is shown and the user presses Backspace three times
- **THEN** the last three digits are cleared and the fourth cell becomes active

#### Scenario: The field is one tab stop

- **WHEN** the user tabs forward from the field
- **THEN** focus moves to the next control on the form, not to another cell

### Requirement: The field is announced as one labelled control

The component SHALL expose a single accessible name — taken from the caller's
label or `aria-label` — rather than presenting six unlabelled boxes, and SHALL
declare `autocomplete="one-time-code"` and a numeric input mode so a phone
offers the numeric keypad and the platform can offer a received code for
autofill. It SHALL accept and forward a `disabled` state and expose an invalid
state so a caller's validation error is reflected on the field.

#### Scenario: The field has one accessible name

- **WHEN** `CodeInput` is rendered with the label "Verification code"
- **THEN** assistive technology reports one field named "Verification code"

#### Scenario: One-time-code autofill is offered

- **WHEN** the field is rendered
- **THEN** it declares `autocomplete="one-time-code"` and a numeric input mode

#### Scenario: Disabled blocks entry

- **WHEN** the field is disabled and the user types a digit
- **THEN** no cell changes and `onChange` is not called

#### Scenario: An invalid code is reflected

- **WHEN** the caller marks the field invalid after a rejected code
- **THEN** the cells render in an error state and the field is marked invalid
  to assistive technology

### Requirement: Both code entry points use the field

The sign-in verification step and the Settings email-verification step SHALL
both collect their code through `CodeInput` rather than a plain text input, so
the two do not drift apart. Adopting it SHALL NOT change what either screen
submits: the value handed to the verification call remains the same code
string.

#### Scenario: Sign-in collects a segmented code

- **WHEN** the sign-in screen asks for the emailed verification code
- **THEN** it renders `CodeInput`, and its existing validation and error
  messaging continue to apply

#### Scenario: Email verification collects a segmented code

- **WHEN** Settings asks for the code sent to a newly added address
- **THEN** it renders `CodeInput`, and Verify, Resend and Cancel remain
  available

#### Scenario: The submitted value is unchanged

- **WHEN** a user completes the code on either screen
- **THEN** the verification call receives the same code string it received
  before this change
