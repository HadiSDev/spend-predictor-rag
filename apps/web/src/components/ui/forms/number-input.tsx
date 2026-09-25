import * as React from 'react'
import { NumericFormat } from 'react-number-format'
import type { NumericFormatProps } from 'react-number-format'
import { cn } from '../cn'
import { inputClassName } from './input'

export type NumberInputProps = NumericFormatProps

/** A formatted numeric input built on `react-number-format`. */
export const NumberInput = React.forwardRef<HTMLInputElement, NumberInputProps>(
  ({ className, ...props }, ref) => (
    <NumericFormat
      getInputRef={ref}
      className={cn(inputClassName, className)}
      {...props}
    />
  ),
)
NumberInput.displayName = 'NumberInput'
