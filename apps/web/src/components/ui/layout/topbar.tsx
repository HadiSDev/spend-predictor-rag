import * as React from 'react'
import { cn } from '../cn'

/** Sticky top bar for a page: put breadcrumbs/title on the left, actions on the right. */
export const Topbar = React.forwardRef<
  HTMLElement,
  React.HTMLAttributes<HTMLElement>
>(({ className, ...props }, ref) => (
  <header
    ref={ref}
    className={cn(
      'flex h-16 shrink-0 items-center justify-between gap-4 px-2 sm:px-4',
      className,
    )}
    {...props}
  />
))
Topbar.displayName = 'Topbar'

export function TopbarTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h1
      className={cn(
        'font-display text-xl font-medium tracking-tight',
        className,
      )}
      {...props}
    />
  )
}

export function TopbarActions({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex items-center gap-2', className)} {...props} />
}
