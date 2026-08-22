import * as React from 'react'
import { cn } from './cn'

export interface CodeInputProps extends Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  'value' | 'onChange' | 'type' | 'maxLength'
> {
  /** The code entered so far. Shorter than `length` while incomplete. */
  value: string
  /** Called with the whole code, never with a single cell's digit. */
  onChange: (code: string) => void
  /**
   * Called once when the last empty cell is filled, by typing or by pasting,
   * so a caller can submit without a further click. Fires on the *transition*
   * into a complete code — editing a digit of an already-complete code does
   * not re-fire it on every keystroke.
   */
  onComplete?: (code: string) => void
  /** How many digits the code has. */
  length?: number
}

/**
 * A one-time code, rendered as one cell per digit.
 *
 * Built on **a single transparent `<input>` stretched over presentational
 * cells**, not one input per cell. Six inputs is the obvious construction and
 * the wrong one: it turns everything the platform gives for free into manual
 * work — one tab stop becomes six plus roving focus, one accessible name
 * becomes six controls to name, native paste fires on a single cell and has to
 * be redistributed, `one-time-code` autofill fills only the focused cell, and
 * there is no single element to forward a react-hook-form ref to.
 *
 * The price is that the caret is ours to manage: the selection is pinned to the
 * end of the value so typing always appends. That deliberately breaks
 * mid-string insertion, which is precisely the operation that would silently
 * produce a code the user did not type.
 */
export const CodeInput = React.forwardRef<HTMLInputElement, CodeInputProps>(
  (
    {
      value,
      onChange,
      onComplete,
      length = 6,
      className,
      disabled,
      onKeyDown,
      ...props
    },
    forwardedRef,
  ) => {
    const innerRef = React.useRef<HTMLInputElement | null>(null)
    const setRef = React.useCallback(
      (node: HTMLInputElement | null) => {
        innerRef.current = node
        if (typeof forwardedRef === 'function') forwardedRef(node)
        else if (forwardedRef) forwardedRef.current = node
      },
      [forwardedRef],
    )

    const digits = value.slice(0, length)
    const [focused, setFocused] = React.useState(false)
    const invalid =
      props['aria-invalid'] === true || props['aria-invalid'] === 'true'

    // The last value we announced as complete. A ref, not state: it must not
    // cause a render, and firing on `digits.length === length` alone would
    // re-fire on every re-render and on every edit of a complete code.
    const completed = React.useRef<string | null>(null)
    React.useEffect(() => {
      if (digits.length < length) {
        completed.current = null
        return
      }
      if (completed.current === digits) return
      completed.current = digits
      onComplete?.(digits)
    }, [digits, length, onComplete])

    /**
     * Collapse the selection to the end, so the next keystroke appends.
     * Guarded: jsdom does not implement `setSelectionRange` on every input
     * type, and a missing implementation should degrade to no pinning rather
     * than throw mid-render.
     */
    function pinCaret() {
      const node = innerRef.current
      if (!node) return
      const end = node.value.length
      try {
        if (node.selectionStart !== end || node.selectionEnd !== end) {
          node.setSelectionRange(end, end)
        }
      } catch {
        // No selection API here — the cells still render from `value`.
      }
    }

    /**
     * One filter for typing, pasting, autofill and IME alike. A `keydown`
     * filter would catch only typing, and would let a pasted `123 456`
     * through with its space intact.
     */
    function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
      if (disabled) return
      const next = event.target.value.replace(/\D/g, '').slice(0, length)
      if (next !== digits) onChange(next)
    }

    function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
      onKeyDown?.(event)
      if (disabled || event.defaultPrevented) return
      // Backspace is ours because the caret is pinned to the end: the native
      // action would already delete the last character, but doing it here
      // keeps deletion consistent when the value and caret ever disagree.
      if (event.key === 'Backspace') {
        event.preventDefault()
        if (digits.length > 0) onChange(digits.slice(0, -1))
        return
      }
      // The active cell is always the entry point, so there is nothing to the
      // left or right to move to. Swallow the arrows rather than let them drag
      // the caret out of position.
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault()
      }
    }

    // Where the ring goes: the first empty cell, clamped to the last one so a
    // complete code still shows focus somewhere.
    const activeIndex = Math.min(digits.length, length - 1)

    return (
      <div
        className={cn(
          'relative w-fit',
          disabled && 'cursor-not-allowed',
          className,
        )}
      >
        <input
          ref={setRef}
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={length}
          value={digits}
          disabled={disabled}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            setFocused(true)
            pinCaret()
          }}
          onBlur={(event) => {
            setFocused(false)
            props.onBlur?.(event)
          }}
          onClick={pinCaret}
          onSelect={pinCaret}
          className={cn(
            'absolute inset-0 z-10 w-full appearance-none bg-transparent text-transparent outline-none',
            'selection:bg-transparent disabled:cursor-not-allowed',
            // The value is drawn by the cells below; the input itself must
            // show neither text nor caret.
            '[caret-color:transparent]',
          )}
          {...props}
        />
        <div
          aria-hidden="true"
          className={cn('flex gap-2', disabled && 'opacity-50')}
        >
          {Array.from({ length }, (_, index) => {
            const digit = digits[index]
            const active = focused && index === activeIndex
            return (
              <div
                key={index}
                data-slot="code-input-cell"
                data-filled={digit ? '' : undefined}
                data-active={active ? '' : undefined}
                className={cn(
                  'flex h-12 w-11 items-center justify-center rounded-md border',
                  'font-mono text-xl tabular-nums transition',
                  // Empty cells sit back — recessed ground, muted border — so
                  // the filled ones read as raised and progress through the
                  // code is legible without counting characters.
                  digit
                    ? 'border-foreground/30 bg-card font-semibold text-foreground shadow-sm'
                    : 'border-input bg-muted/50 text-muted-foreground',
                  // The same focus treatment every other control in the library
                  // uses, applied to the cell since the row has no visible box.
                  active && 'border-ring bg-card ring-2 ring-ring',
                  invalid && 'border-destructive',
                )}
              >
                {digit}
              </div>
            )
          })}
        </div>
      </div>
    )
  },
)
CodeInput.displayName = 'CodeInput'
