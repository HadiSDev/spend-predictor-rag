import * as React from 'react'
import { Tabs as BaseTabs } from '@base-ui-components/react/tabs'
import { cn } from '../cn'

export const Tabs = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseTabs.Root>
>(({ className, ...props }, ref) => (
  <BaseTabs.Root
    ref={ref}
    className={cn('flex flex-col gap-4', className)}
    {...props}
  />
))
Tabs.displayName = 'Tabs'

export const TabsList = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseTabs.List>
>(({ className, children, ...props }, ref) => (
  <BaseTabs.List
    ref={ref}
    className={cn(
      'inline-flex items-center gap-1 rounded-full bg-muted p-1 text-muted-foreground',
      className,
    )}
    {...props}
  >
    {children}
  </BaseTabs.List>
))
TabsList.displayName = 'TabsList'

export const TabsTab = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof BaseTabs.Tab>
>(({ className, ...props }, ref) => (
  <BaseTabs.Tab
    ref={ref}
    className={cn(
      'relative inline-flex h-8 items-center justify-center rounded-full px-4 text-sm font-medium whitespace-nowrap outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring hover:text-foreground data-[active]:bg-primary data-[active]:text-primary-foreground data-[active]:shadow-sm data-[active]:hover:text-primary-foreground',
      className,
    )}
    {...props}
  />
))
TabsTab.displayName = 'TabsTab'

export const TabsPanel = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseTabs.Panel>
>(({ className, ...props }, ref) => (
  <BaseTabs.Panel
    ref={ref}
    className={cn('outline-none', className)}
    {...props}
  />
))
TabsPanel.displayName = 'TabsPanel'
