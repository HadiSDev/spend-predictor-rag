import * as React from 'react'
import { cn } from '../cn'

export const Sidebar = React.forwardRef<
  HTMLElement,
  React.HTMLAttributes<HTMLElement>
>(({ className, ...props }, ref) => (
  <aside
    ref={ref}
    className={cn(
      'flex w-64 shrink-0 flex-col gap-4 rounded-card bg-card p-4 text-card-foreground shadow-card',
      className,
    )}
    {...props}
  />
))
Sidebar.displayName = 'Sidebar'

export function SidebarHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex items-center gap-2 px-2 py-1', className)}
      {...props}
    />
  )
}

export function SidebarContent({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex-1 overflow-y-auto', className)} {...props} />
}

export function SidebarFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('mt-auto', className)} {...props} />
}

export function SidebarNav({
  className,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  return <nav className={cn('flex flex-col gap-1', className)} {...props} />
}

/** Class for a nav item — reuse to style a router `<Link>` directly. */
export function sidebarNavItemClass(active?: boolean) {
  return cn(
    'flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring [&_svg]:size-5 [&_svg]:shrink-0',
    active
      ? 'bg-primary text-primary-foreground'
      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
  )
}

export interface SidebarNavItemProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: React.ReactNode
  active?: boolean
}

export const SidebarNavItem = React.forwardRef<
  HTMLButtonElement,
  SidebarNavItemProps
>(({ className, icon, active, children, type = 'button', ...props }, ref) => (
  <button
    ref={ref}
    type={type}
    className={cn(sidebarNavItemClass(active), className)}
    {...props}
  >
    {icon}
    <span className="truncate">{children}</span>
  </button>
))
SidebarNavItem.displayName = 'SidebarNavItem'
