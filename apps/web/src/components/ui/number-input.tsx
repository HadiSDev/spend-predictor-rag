import * as React from 'react'
import { NumericFormat, type NumericFormatProps } from 'react-number-format'
import { cn } from './cn'
import { inputClassName } from './input'

export type NumberInputProps = NumericFormatProps

/**
 * A formatted numeric input built on `react-number-format`. Pass any
 * NumericFormat props — e.g. `thousandSeparator`, `decimalScale`,
 * `fixedDecimalScale`, `prefix`/`suffix`, `allowNegative`, `value`,
 * `onValueChange`. Styled with the shared input tokens.
 */
export const NumberInput = React.forwardRef<HTMLInputElement, NumberInputProps>(
  ({ className, ...props }, ref) => (
    <NumericFormat getInputRef={ref} className={cn(inputClassName, className)} {...props} />
  ),
)
NumberInput.displayName = 'NumberInput'
