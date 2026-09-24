## 1. The component

- [x] 1.1 Create `apps/web/src/components/ui/code-input.tsx` with a
  `CodeInputProps` typed on `value`, `onChange(code: string)`, optional
  `onComplete(code: string)`, `length` (default 6), `disabled`, `aria-invalid`,
  and the remaining input attributes; forward the ref to the real `<input>` so
  react-hook-form's `FormField` can register it.
- [x] 1.2 Render one transparent full-width `<input>` over a row of `length`
  presentational cells, each cell reading its character from `value[i]`. Set
  `inputMode="numeric"`, `autoComplete="one-time-code"`, `maxLength={length}`,
  and transparent text *and* caret colour on the input.
- [x] 1.3 Filter in `onChange`: strip non-digits, truncate to `length`, and call
  the caller's `onChange` with the resulting string — one path covering typing,
  paste, and autofill (design: "Filtering happens in `onChange`").
- [x] 1.4 Pin the selection to the end of the value on `focus`, `click` and
  `select`, guarded so a missing `setSelectionRange` degrades to no-pinning
  rather than throwing (jsdom).
- [x] 1.5 Derive the active cell as `min(value.length, length - 1)` and give it
  the `ring-2 ring-ring` treatment; style empty vs filled cells from the
  `border-input` / `bg-card` / `rounded-md` token vocabulary in
  `inputClassName`, and render `aria-invalid` as `border-destructive`.
- [x] 1.6 Handle `keydown` for Backspace (clear the last entered digit). Arrows
  are swallowed, not navigational — see the amended spec and design.
- [x] 1.7 Fire `onComplete` from a ref-guarded effect: only when the code is
  complete *and* differs from the last value fired for; clear the ref when the
  code becomes incomplete, so it never re-fires on re-render or while editing a
  complete code.
- [x] 1.8 Honour `disabled`: no cell changes and no `onChange` while disabled.
- [x] 1.9 Export `CodeInput` and `CodeInputProps` from
  `apps/web/src/components/ui/index.ts`.

## 2. Component tests

- [x] 2.1 Add a `describe('CodeInput')` block to
  `apps/web/src/components/ui/ui.test.tsx`, following the existing
  `NumberInput` block's shape.
- [x] 2.2 Cover structure: `length={6}` renders six cells; `length={4}` renders
  four; a value shorter than `length` fills only its own cells.
- [x] 2.3 Cover entry: typing a digit reports the accumulated string via
  `onChange`; typing a non-digit changes nothing; the field is empty with no
  placeholder digit.
- [x] 2.4 Cover deletion: Backspace on a filled active cell clears it;
  Backspace on an empty active cell clears the previous one.
- [x] 2.5 Cover paste: `123456` fills all six cells; `123 456` strips the space;
  `1234567890` keeps the first six digits only.
- [x] 2.6 Cover completion: `onComplete` fires once on the sixth digit, once on
  a full paste, not at five digits, and not again on a re-render with an
  unchanged complete value.
- [x] 2.7 Cover accessibility: the field exposes one accessible name from its
  label, declares `autocomplete="one-time-code"` and a numeric input mode, is a
  single tab stop, and blocks entry when disabled.

## 3. Adopt on the sign-in screen

- [x] 3.1 In `apps/web/src/routes/sign-in.tsx`, replace the `Input` inside the
  code `FormField` with `CodeInput`, keeping the `FormLabel`, `FormControl`,
  `FormMessage` and the `required` rule; drop the `123456` placeholder and the
  now-redundant `inputMode`/`autoComplete` props.
- [x] 3.2 Wire `onComplete` to submit the code form, so a pasted code verifies
  without a click; leave the Verify button as the retry path.
- [x] 3.3 Update `apps/web/src/routes/sign-in.test.tsx` to drive the new
  control, and add a case asserting a completed code submits on its own.

## 4. Adopt in the Settings emails panel

- [x] 4.1 In `apps/web/src/components/settings/emails-panel.tsx`, replace the
  code `Input` with `CodeInput`, carrying the `aria-label="Verification code"`
  across and dropping the `max-w-40` (the field now sizes itself).
- [x] 4.2 Wire `onComplete` to `handleVerify`, guarded by `busy` so an in-flight
  verification is not submitted twice; keep Verify, Resend and Cancel.
- [x] 4.3 Check the code row's `flex-wrap` layout still reads correctly with the
  wider cell row beside three buttons; wrap the buttons to their own line if it
  crowds.
- [x] 4.4 Update `apps/web/src/components/settings/emails-panel.test.tsx` to
  drive the new control.

## 5. Verify

- [x] 5.1 Run `./node_modules/.bin/vitest run` in `apps/web/` and confirm the UI,
  sign-in, and emails-panel suites pass.
- [x] 5.2 Run `./node_modules/.bin/eslint` in `apps/web/` and clear every error
  in the touched files. **`prettier --check .` is not a usable gate here**: it
  fails on 138 files on a clean tree, so the added code matches the prevailing
  style of the file it sits in instead. Baseline eslint was 47 errors; the
  errors this change introduced are fixed, and the remainder are pre-existing.
- [ ] 5.3 Check the field by hand in both places — type a code, paste
  `123 456`, backspace through it, tab past it, and confirm it renders in both
  light and dark theme.
