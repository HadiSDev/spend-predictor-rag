import * as React from 'react'
import { Tooltip as BaseTooltip } from '@base-ui-components/react/tooltip'
import { cn } from '../cn'

/** Wrap the app (or a subtree) once to enable tooltips. */
export const TooltipProvider = BaseTooltip.Provider
export const Tooltip = BaseTooltip.Root
export const TooltipTrigger = BaseTooltip.Trigger

export const TooltipContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseTooltip.Popup> & { sideOffset?: number }
>(({ className, children, sideOffset = 6, ...props }, ref) => (
  <BaseTooltip.Portal>
    <BaseTooltip.Positioner className="z-50" sideOffset={sideOffset}>
      <BaseTooltip.Popup
        ref={ref}
        className={cn(
          'rounded-md bg-inverted px-2.5 py-1.5 text-xs font-medium text-inverted-foreground shadow-popover transition duration-150 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0',
          className,
        )}
        {...props}
      >
        {children}
      </BaseTooltip.Popup>
    </BaseTooltip.Positioner>
  </BaseTooltip.Portal>
))
TooltipContent.displayName = 'TooltipContent'
