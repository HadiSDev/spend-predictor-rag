import * as React from 'react'
import { Popover as BasePopover } from '@base-ui-components/react/popover'
import { cn } from '../cn'

export const Popover = BasePopover.Root
export const PopoverTrigger = BasePopover.Trigger
export const PopoverClose = BasePopover.Close

export const PopoverContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BasePopover.Popup> & {
    sideOffset?: number
    align?: 'start' | 'center' | 'end'
  }
>(
  (
    { className, children, sideOffset = 8, align = 'center', ...props },
    ref,
  ) => (
    <BasePopover.Portal>
      <BasePopover.Positioner
        className="z-50 outline-none"
        sideOffset={sideOffset}
        align={align}
      >
        <BasePopover.Popup
          ref={ref}
          className={cn(
            'w-72 origin-[var(--transform-origin)] rounded-lg border border-border bg-popover p-4 text-popover-foreground shadow-popover outline-none transition duration-150 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0',
            className,
          )}
          {...props}
        >
          {children}
        </BasePopover.Popup>
      </BasePopover.Positioner>
    </BasePopover.Portal>
  ),
)
PopoverContent.displayName = 'PopoverContent'

export const PopoverTitle = React.forwardRef<
  HTMLHeadingElement,
  React.ComponentProps<typeof BasePopover.Title>
>(({ className, ...props }, ref) => (
  <BasePopover.Title
    ref={ref}
    className={cn('text-sm font-medium', className)}
    {...props}
  />
))
PopoverTitle.displayName = 'PopoverTitle'

export const PopoverDescription = React.forwardRef<
  HTMLParagraphElement,
  React.ComponentProps<typeof BasePopover.Description>
>(({ className, ...props }, ref) => (
  <BasePopover.Description
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  />
))
PopoverDescription.displayName = 'PopoverDescription'
