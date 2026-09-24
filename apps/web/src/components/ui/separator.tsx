import * as React from 'react'
import { Separator as BaseSeparator } from '@base-ui-components/react/separator'
import { cn } from './cn'

export const Separator = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseSeparator>
>(({ className, orientation = 'horizontal', ...props }, ref) => (
  <BaseSeparator
    ref={ref}
    orientation={orientation}
    className={cn(
      'shrink-0 bg-border',
      orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
      className,
    )}
    {...props}
  />
))
Separator.displayName = 'Separator'
