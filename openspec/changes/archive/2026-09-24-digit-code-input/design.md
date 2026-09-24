## Context

Two screens collect a one-time code today, each with its own plain `Input`:
`routes/sign-in.tsx` (inside a `FormField`, validated by react-hook-form) and
`components/settings/emails-panel.tsx` (local `useState`, an `aria-label`, and a
`max-w-40`). Both carry `inputMode="numeric"` and
`autoComplete="one-time-code"` already, so platform autofill works and must not
regress.

Constraints that shape the design:

- **The library's controls are built on Base UI**, but Base UI ships no
  one-time-code primitive (only a plain `input`). There is nothing to wrap.
- **`inputClassName` in `ui/input.tsx` is the shared field shape.** Its comment
  records that the date picker once drifted into looking like a pill beside two
  rounded rectangles, which is exactly what that constant exists to prevent. A
  code field is a different shape by intent — a row of cells, not one box — so
  it does not reuse `inputClassName` wholesale, but it must take its border,
  radius, ring, and disabled treatment from the same tokens.
- **`sign-in.tsx` wires the field through react-hook-form's `FormField`.** Its
  `field` object supplies `value`, `onChange`, `onBlur`, `name` and `ref`, so
  the component has to be controlled and ref-forwarding to drop in without the
  route learning anything about cells.

## Goals / Non-Goals

**Goals:**

- One `CodeInput` in `ui/`, used by both screens, that reads as part of the
  existing control set.
- Progress through the code is visible; the field states its own length.
- Paste, platform autofill, and the numeric keypad all keep working.
- One tab stop, one accessible name, full keyboard editing.
- `onComplete` so a pasted code verifies with no further click.

**Non-Goals:**

- **No alphanumeric or masked mode.** Both call sites take a numeric Clerk code.
  A `pattern`/`type` prop is speculative generality; add it when a second kind
  of code exists.
- **No resend timer, no countdown, no auto-focus-on-mount.** Resend already
  exists in the emails panel as a button; stealing focus on mount is a separate
  decision affecting both screens.
- **No change to what is submitted.** The verification call receives the same
  string, so nothing server-side moves.
- **No new dependency.**

## Decisions

### One real input behind presentational cells — not six inputs

The component renders **a single `<input>`**, visually transparent and stretched
across the row, with the cells rendered as non-interactive `<div>`s beneath it
reading their character from `value`.

Alternative considered: **six `<input>` elements**, one per cell — the obvious
construction, and the one most hand-rolled OTP fields use. Rejected because
almost every requirement in the spec becomes manual work that the platform
otherwise does for free:

| Concern | One input | Six inputs |
| --- | --- | --- |
| Tab stops | one, natively | six; needs `tabIndex={-1}` on five and roving focus |
| Accessible name | one label, one control | six controls to name, or an ARIA group to invent |
| Paste | native `paste` on the focused field | fires on one cell; must be intercepted and redistributed |
| `one-time-code` autofill | works as on any input | browsers fill only the focused cell |
| Backspace / arrows | caret movement, mostly native | fully hand-written focus juggling |
| react-hook-form `ref` | forwards to the one input | no single element to forward to |

The cost is that the caret is drawn by us rather than by the browser (see
below), and that the cells must not be reachable by pointer individually — a
click anywhere on the row focuses the one input, which is the behaviour a user
expects from a code field anyway.

### Selection is pinned to the end, and the "active cell" is derived

With one input, the caret can land mid-string, and a user typing there would
insert rather than overwrite — producing a code whose cells no longer match what
they typed. On focus, click, and selection change, the component **collapses the
selection to the end of the value**. The active cell is then always
`value.length` (clamped to the last index), which is what the spec's "focus
lands where input is needed" and "the fourth cell carries the focus ring"
requirements describe.

Consequence, accepted: **there is no arrow navigation.** The alternative was an
*editing index* separate from `value.length`, which arrows move and typing
overwrites. Rejected: it means digit entry has to leave `onChange` for explicit
`keydown` handling, leaving two input paths (typed vs. pasted/autofilled) to
keep in sync — and it buys an affordance that the code fields users already know
(input-otp, Clerk's own, GitHub's) do not offer. Arrows are swallowed rather
than left to drag the caret out of position, and a wrong digit is corrected by
Backspace.

Backspace is handled on `keydown` rather than left to the native action: with
the caret pinned, the native delete would already remove the last character, but
owning it keeps deletion correct if the value and the caret ever disagree.

### Filtering happens in `onChange`, not `onKeyDown`

`onChange` receives the input's whole next value; the component strips
non-digits, truncates to `length`, and reports the result. This handles typing,
pasting, autofill, and IME input through one path — a `keydown` filter catches
only typing, and would let a pasted `123 456` through unfiltered. `maxLength` is
set as a second line of defence, not the primary one.

Because filtering is by value, the "non-digits are rejected" requirement falls
out: a rejected character produces the same value as before, so `onChange` to
the caller either does not fire or fires with an unchanged string.

### `onComplete` fires on the transition, tracked by a ref

Firing whenever `value.length === length` would re-fire on every re-render and
on every keystroke that edits an already-complete code — auto-submitting a code
the user is in the middle of correcting. The component keeps the last value it
fired for in a ref and fires only when the code is complete **and** differs from
that value; an incomplete value clears the ref, so re-completing fires again.

Alternative considered: firing from `onChange` only, never from an effect. This
misses autofill in browsers that set the value without a React change event.
The ref-guarded effect covers both and is idempotent.

### Styling: derived from the field tokens, one cell per digit

Cells use `border-input`, `bg-card`, the `rounded-md` radius and
`focus-visible:ring-ring` treatment from `inputClassName`'s vocabulary, sized
square (`h-12 w-10`) with a tabular, larger digit. Three states:

- **empty** — `border-input`, muted background
- **filled** — `border-ring`-weight border and `text-foreground`
- **active** — the `ring-2 ring-ring` the rest of the library uses for focus,
  applied to the cell rather than the row, since the row has no visible box

Invalid comes from the caller (`aria-invalid`), rendered as `border-destructive`
— the token `FormMessage`/`FieldError` already uses, so the field and its error
text agree.

A gap after the midpoint is **not** added: it only reads correctly for even
lengths, and hard-codes an assumption about grouping that a `length` prop
otherwise avoids.

## Risks / Trade-offs

- **The caret is simulated, so an unusual input method could desync it from the
  cells** → Selection is re-pinned on `select`, `focus`, and `click`, and the
  rendered cells always derive from `value`, never from caret state — so the
  display cannot disagree with the submitted string even if the caret does.
- **Pinning the selection breaks native text editing (double-click select-all,
  mid-string insertion)** → Accepted, and intended: a code field is positional,
  and mid-string insertion is precisely the operation that would silently
  produce the wrong code. Ctrl/Cmd+A and paste still work.
- **Transparent-text tricks can render the value visible on some platforms** (a
  visible caret, or a native autofill overlay) → The input uses transparent
  colour *and* transparent caret; the autofill overlay is a platform affordance
  and appearing over the cells is harmless.
- **The two screens' existing tests type into a plain input** → They drive the
  field by typing into the one real input, which is still an input with an
  accessible name, so the tests change how they query it, not how they type.
- **jsdom does not implement `setSelectionRange` identically to browsers** →
  Selection pinning is guarded so a missing implementation degrades to
  no-pinning rather than throwing; the value-level logic that the tests assert
  on does not depend on it.

## Migration Plan

Additive and reversible. `CodeInput` lands first with its own tests, then each
call site swaps `Input` → `CodeInput` in a separate step, so a problem at one
screen does not hold up the other. No data, API, or schema change; rollback is
reverting the component swap at either screen, since the submitted value is
unchanged either way.

## Open Questions

- **Should focus land on the field automatically when the verification step
  appears?** It is the only thing on the screen at that moment, so it is
  probably right — but it is a decision about the two *screens*, not the
  component, and auto-focus interacts with the emails panel where the code form
  appears below an existing list. Left out; easy to add later at either call
  site.
- **Should a rejected code clear the field?** Today neither screen clears on
  error. Retyping over a complete code works, so this is a polish question for
  whoever next touches the verification flows.
