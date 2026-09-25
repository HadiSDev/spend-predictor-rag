import * as React from 'react'
import { cn } from '../cn'

export interface CodeInputProps extends Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  'value' | 'onChange' | 'type' | 'maxLength'
> {
  /** The code entered so far. Shorter than `length` while incomplete. */
  value: string
  /** Called with the whole code, never with a single cell's digit. */
  onChange: (code: string) => void
  /** Called once when the code becomes complete, by typing or by pasting. */
  onComplete?: (code: string) => void
  /** How many digits the code has. */
  length?: number
}

/** A one-time code input: one transparent input over one presentational cell per digit. */
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
        if (typeof forwardedRef === 'function') {
          forwardedRef(node)
        } else if (forwardedRef) {
          forwardedRef.current = node
        }
      },
      [forwardedRef],
    )

    const digits = value.slice(0, length)
    const [focused, setFocused] = React.useState(false)
    const invalid =
      props['aria-invalid'] === true || props['aria-invalid'] === 'true'

    const lastCompletedCode = React.useRef<string | null>(null)
    React.useEffect(() => {
      if (digits.length < length) {
        lastCompletedCode.current = null
        return
      }
      if (lastCompletedCode.current === digits) {
        return
      }
      lastCompletedCode.current = digits
      onComplete?.(digits)
    }, [digits, length, onComplete])

    /** Collapse the selection to the end, so the next keystroke appends. */
    function pinCaret() {
      const node = innerRef.current
      if (!node) {
        return
      }
      const end = node.value.length
      try {
        if (node.selectionStart !== end || node.selectionEnd !== end) {
          node.setSelectionRange(end, end)
        }
      } catch {
        return
      }
    }

    function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
      if (disabled) {
        return
      }
      const next = event.target.value.replace(/\D/g, '').slice(0, length)
      if (next !== digits) {
        onChange(next)
      }
    }

    function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
      onKeyDown?.(event)
      if (disabled || event.defaultPrevented) {
        return
      }
      if (event.key === 'Backspace') {
        event.preventDefault()
        if (digits.length > 0) {
          onChange(digits.slice(0, -1))
        }
        return
      }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault()
      }
    }

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
                  digit
                    ? 'border-foreground/30 bg-card font-semibold text-foreground shadow-sm'
                    : 'border-input bg-muted/50 text-muted-foreground',
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
