import * as React from 'react'
import { Checkbox as BaseCheckbox } from '@base-ui-components/react/checkbox'
import { Check, Minus } from 'lucide-react'
import { cn } from '../cn'

export const Checkbox = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof BaseCheckbox.Root>
>(({ className, ...props }, ref) => (
  <BaseCheckbox.Root
    ref={ref}
    className={cn(
      'group grid size-5 shrink-0 place-items-center rounded-[6px] border border-input bg-card text-primary-foreground outline-none transition focus-visible:ring-2 focus-visible:ring-ring data-[checked]:border-primary data-[checked]:bg-primary data-[indeterminate]:border-primary data-[indeterminate]:bg-primary disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...props}
  >
    <BaseCheckbox.Indicator className="flex text-current">
      <Check className="size-3.5 group-data-[indeterminate]:hidden" />
      <Minus className="hidden size-3.5 group-data-[indeterminate]:block" />
    </BaseCheckbox.Indicator>
  </BaseCheckbox.Root>
))
Checkbox.displayName = 'Checkbox'
