import * as React from 'react'
import { Switch as BaseSwitch } from '@base-ui-components/react/switch'
import { cn } from './cn'

export const Switch = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof BaseSwitch.Root>
>(({ className, ...props }, ref) => (
  <BaseSwitch.Root
    ref={ref}
    className={cn(
      'relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full bg-input outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring data-[checked]:bg-primary disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...props}
  >
    {/* Checked, the thumb takes the ink's counter-colour: in dark mode the
        checked track *is* white, and a hard-coded white thumb vanished on it. */}
    <BaseSwitch.Thumb className="size-5 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform data-[checked]:translate-x-[22px] data-[checked]:bg-primary-foreground" />
  </BaseSwitch.Root>
))
Switch.displayName = 'Switch'
