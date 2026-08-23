import * as React from 'react'
import { cn } from './cn'
import { NumberInput, type NumberInputProps } from './number-input'

/**
 * How a currency writes an amount: its symbol, which side it sits on, and how
 * the locale groups digits.
 *
 * Derived from `Intl.NumberFormat` rather than a hand-kept symbol table, for
 * the same reason `lib/format.ts::formatMoney` uses it — a field and the
 * read-only echo beside it must not disagree about how DKK is written.
 *
 * An unknown code falls back to the code itself as a suffix, which is what
 * `formatMoney` does too. A field is never left refusing to render because a
 * connector sent something `Intl` has not heard of.
 */
function conventionFor(currency: string | null): {
  prefix?: string
  suffix?: string
} {
  if (!currency) return {}
  try {
    const parts = new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency,
      currencyDisplay: 'narrowSymbol',
    }).formatToParts(0)
    const index = parts.findIndex((part) => part.type === 'currency')
    if (index === -1) return { suffix: ` ${currency}` }
    const symbol = parts[index].value
    // Leading in most locales (`£1,234.56`), trailing in some (`1 234,56 kr`).
    return index === 0 ? { prefix: `${symbol} ` } : { suffix: ` ${symbol}` }
  } catch {
    // An invalid ISO code. Show it rather than dropping it — a reviewer seeing
    // "XYZ" learns something; a bare number tells them nothing.
    return { suffix: ` ${currency}` }
  }
}

export interface CurrencyInputProps
  extends Omit<NumberInputProps, 'value' | 'onChange' | 'onValueChange'> {
  /** ISO 4217 code the amount is in. Null renders a plain 2-decimal number —
   *  a line whose invoice states no currency is an ordinary case. */
  currency: string | null
  /** The stored amount. A string is accepted because the API sends Decimals as
   *  strings, so a caller never has to parse before rendering. */
  value: string | number | null | undefined
  /**
   * The parsed amount, or `null` for an empty field.
   *
   * **Never a string and never `NaN`.** The bug this component exists to end
   * was `Number(input.value)` at the call site: `Number('1,5')` is `NaN`, which
   * serializes to JSON `null`, which the API reads as "clear this field" — so a
   * reviewer typing a European decimal erased the figure and was told nothing.
   */
  onChange: (value: number | null) => void
}

/**
 * A money field bound to a currency.
 *
 * Two decimal places, fixed: every monetary column in this system is
 * `Numeric(14,2)`, so the control shows exactly what can be stored. Quantities
 * and unit prices are `Numeric(12,4)` and deliberately use `NumberInput`
 * directly at a wider scale — clamping those to 2 would round a stored value on
 * save, changing data nobody asked to change.
 */
export const CurrencyInput = React.forwardRef<HTMLInputElement, CurrencyInputProps>(
  ({ currency, value, onChange, className, ...props }, ref) => {
    const convention = conventionFor(currency)
    return (
      <NumberInput
        getInputRef={ref}
        // `?? ''` rather than `?? 0`: an unset amount is an empty field, not a
        // zero a reviewer has to notice is wrong and clear.
        value={value ?? ''}
        onValueChange={(values) => {
          // `floatValue` is undefined for an empty field and for input the
          // formatter could not read — both mean "no figure", which is null.
          onChange(values.floatValue ?? null)
        }}
        thousandSeparator=","
        decimalScale={2}
        fixedDecimalScale
        // A negative line is real — a credit note reduces spend — so negatives
        // are allowed rather than silently dropped.
        allowNegative
        inputMode="decimal"
        {...convention}
        // Right-aligned tabular figures: a column of amounts is meant to be
        // scanned down, and proportional digits make that impossible.
        className={cn('text-right tabular-nums', className)}
        {...props}
      />
    )
  },
)
CurrencyInput.displayName = 'CurrencyInput'
