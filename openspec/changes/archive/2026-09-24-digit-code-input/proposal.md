## Why

A one-time code is the only thing standing between a customer and their ledger,
and today we ask for it with a bare `Input` carrying a `123456` placeholder. It
gives the user nothing: no statement of how many digits are wanted, no visible
progress through them, and a placeholder that reads as a filled-in value at a
glance. The two places we collect a code — signing in, and verifying a new email
address in Settings — have drifted apart already (one has a label and a form
field, the other an `aria-label` and a `max-w-40`), so the fix belongs in the UI
library rather than in either screen.

## What Changes

- **New `CodeInput` in `apps/web/src/components/ui/`** — a segmented one-time-code
  field rendering one cell per digit, exported from the `ui/` barrel like every
  other control.
- **The cell count is a prop, not a constant.** Six is the default because that
  is what Clerk sends, but a component that hard-codes it is a component we
  rewrite the first time a code is a different length.
- **Progress is visible.** Filled and empty cells are distinguishable, and the
  cell awaiting input carries the focus ring — so "3 of 6 entered" is readable
  without counting characters.
- **Paste fills the whole code.** Pasting `123456` — or `123 456`, since mail
  clients group them — distributes across the cells rather than landing entirely
  in the first one. Non-digits are discarded rather than occupying a cell.
- **The component auto-submits on completion** via an `onComplete` callback, so a
  pasted code verifies without a further click. The Verify button stays: it is
  the retry path, and the keyboard path for anyone who edits a digit after
  completing.
- **Both call sites adopt it** — `routes/sign-in.tsx` (inside its existing
  `FormField`, so validation and error messaging are untouched) and
  `components/settings/emails-panel.tsx`.
- Keyboard and assistive-technology behaviour is specified, not incidental:
  arrow keys and Backspace move between cells, and the group is announced as one
  labelled field rather than six unlabelled boxes.

## Capabilities

### New Capabilities

- `frontend-code-input`: the segmented one-time-code field — its structure,
  digit entry and deletion, paste distribution, completion callback, keyboard
  navigation, and accessible name.

### Modified Capabilities

<!-- None. `frontend-ui-library` already requires "a comprehensive component set
     exported from ui/" built on accessible primitives with token-driven
     styling; CodeInput satisfies those existing requirements rather than
     changing them. The two call sites change which control they render, which
     is implementation, not spec-level behaviour: `frontend-auth-dashboard` and
     `frontend-settings` still require a code to be collected and submitted. -->

## Impact

- **New**: `apps/web/src/components/ui/code-input.tsx`, plus its export line in
  `apps/web/src/components/ui/index.ts` and coverage in
  `apps/web/src/components/ui/ui.test.tsx`.
- **Changed**: `apps/web/src/routes/sign-in.tsx` and
  `apps/web/src/components/settings/emails-panel.tsx` swap `Input` for
  `CodeInput`. Both have existing tests (`sign-in.test.tsx`,
  `emails-panel.test.tsx`) that type into the code field and will need to drive
  the new control.
- **No dependency added.** Base UI ships no one-time-code primitive, and the
  behaviour is a controlled input plus key handling — not worth a package.
- **No backend, API, or schema impact.** The submitted value is the same string.
