import * as React from 'react'
import { cn } from '../cn'
import { NumberInput } from './number-input'
import type { NumberInputProps } from './number-input'

/** The currency symbol placement for an amount, derived from `Intl.NumberFormat`. */
function conventionFor(currency: string | null): {
  prefix?: string
  suffix?: string
} {
  if (!currency) {
    return {}
  }
  try {
    const parts = new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency,
      currencyDisplay: 'narrowSymbol',
    }).formatToParts(0)
    const index = parts.findIndex((part) => part.type === 'currency')
    if (index === -1) {
      return { suffix: ` ${currency}` }
    }
    const symbol = parts[index].value
    return index === 0 ? { prefix: `${symbol} ` } : { suffix: ` ${symbol}` }
  } catch {
    return { suffix: ` ${currency}` }
  }
}

export interface CurrencyInputProps extends Omit<
  NumberInputProps,
  'value' | 'onChange' | 'onValueChange'
> {
  /** ISO 4217 code the amount is in. Null renders a plain 2-decimal number. */
  currency: string | null
  /** The stored amount, as a number or a decimal string. */
  value: string | number | null | undefined
  /** The parsed amount, or `null` for an empty field. */
  onChange: (value: number | null) => void
}

/** A two-decimal money field bound to a currency. */
export const CurrencyInput = React.forwardRef<
  HTMLInputElement,
  CurrencyInputProps
>(({ currency, value, onChange, className, ...props }, ref) => {
  const convention = conventionFor(currency)
  return (
    <NumberInput
      getInputRef={ref}
      value={value ?? ''}
      onValueChange={(values) => {
        onChange(values.floatValue ?? null)
      }}
      thousandSeparator=","
      decimalScale={2}
      fixedDecimalScale
      allowNegative
      inputMode="decimal"
      {...convention}
      className={cn('text-right tabular-nums', className)}
      {...props}
    />
  )
})
CurrencyInput.displayName = 'CurrencyInput'
