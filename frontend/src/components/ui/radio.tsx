import * as React from 'react'
import { RadioGroup as BaseRadioGroup } from '@base-ui-components/react/radio-group'
import { Radio as BaseRadio } from '@base-ui-components/react/radio'
import { cn } from './cn'

export const RadioGroup = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseRadioGroup>
>(({ className, ...props }, ref) => (
  <BaseRadioGroup ref={ref} className={cn('flex flex-col gap-2', className)} {...props} />
))
RadioGroup.displayName = 'RadioGroup'

export const RadioItem = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof BaseRadio.Root>
>(({ className, ...props }, ref) => (
  <BaseRadio.Root
    ref={ref}
    className={cn(
      'grid size-5 shrink-0 place-items-center rounded-full border border-input bg-card outline-none transition focus-visible:ring-2 focus-visible:ring-ring data-[checked]:border-primary disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...props}
  >
    <BaseRadio.Indicator className="size-2.5 rounded-full bg-primary data-[unchecked]:hidden" />
  </BaseRadio.Root>
))
RadioItem.displayName = 'RadioItem'
