import * as React from 'react'
import { Menu } from '@base-ui-components/react/menu'
import { cn } from '../cn'

export const DropdownMenu = Menu.Root
export const DropdownMenuTrigger = Menu.Trigger
export const DropdownMenuGroup = Menu.Group

export const DropdownMenuContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof Menu.Popup> & {
    sideOffset?: number
    align?: 'start' | 'center' | 'end'
  }
>(({ className, children, sideOffset = 6, align = 'start', ...props }, ref) => (
  <Menu.Portal>
    <Menu.Positioner
      className="z-50 outline-none"
      sideOffset={sideOffset}
      align={align}
    >
      <Menu.Popup
        ref={ref}
        className={cn(
          'min-w-40 origin-[var(--transform-origin)] rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover outline-none transition duration-150 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0',
          className,
        )}
        {...props}
      >
        {children}
      </Menu.Popup>
    </Menu.Positioner>
  </Menu.Portal>
))
DropdownMenuContent.displayName = 'DropdownMenuContent'

export const DropdownMenuItem = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof Menu.Item>
>(({ className, ...props }, ref) => (
  <Menu.Item
    ref={ref}
    className={cn(
      'flex cursor-default items-center gap-2 rounded-md px-3 py-1.5 text-sm outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-muted [&_svg]:size-4 [&_svg]:text-muted-foreground',
      className,
    )}
    {...props}
  />
))
DropdownMenuItem.displayName = 'DropdownMenuItem'

export const DropdownMenuLabel = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof Menu.GroupLabel>
>(({ className, ...props }, ref) => (
  <Menu.GroupLabel
    ref={ref}
    className={cn(
      'px-3 py-1.5 text-xs font-medium text-muted-foreground',
      className,
    )}
    {...props}
  />
))
DropdownMenuLabel.displayName = 'DropdownMenuLabel'

export const DropdownMenuSeparator = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof Menu.Separator>
>(({ className, ...props }, ref) => (
  <Menu.Separator
    ref={ref}
    className={cn('-mx-1 my-1 h-px bg-border', className)}
    {...props}
  />
))
DropdownMenuSeparator.displayName = 'DropdownMenuSeparator'
