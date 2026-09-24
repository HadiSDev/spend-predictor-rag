import * as React from 'react'
import { cn } from './cn'

export const inputClassName =
  'flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground shadow-sm outline-none transition placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50'

/**
 * The same field shape, for controls that *look* like an input but are buttons:
 * the select trigger, the combobox trigger, the date picker.
 *
 * Shared rather than repeated because these sit side by side in filter rows,
 * and the moment they drift they stop reading as one set of controls. The date
 * picker used `Button variant="outline"` and so rendered as a transparent pill
 * beside two rounded-rectangle fields — which is what this constant exists to
 * prevent recurring.
 *
 * Both `disabled:` and `data-[disabled]:` are set: the first covers a native
 * `<button>`, the second Base UI's own disabled state.
 */
export const fieldTriggerClassName =
  'flex h-10 w-full items-center justify-between gap-2 rounded-md border border-input bg-card px-3 text-sm text-foreground outline-none transition focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50'

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = 'text', ...props }, ref) => (
    <input ref={ref} type={type} className={cn(inputClassName, className)} {...props} />
  ),
)
Input.displayName = 'Input'
