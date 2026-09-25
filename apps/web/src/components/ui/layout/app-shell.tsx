import * as React from 'react'
import { cn } from '../cn'

export interface AppShellProps {
  /** The sidebar element (use the `Sidebar` component). */
  sidebar: React.ReactNode
  /** Optional top bar (use the `Topbar` component). */
  header?: React.ReactNode
  children: React.ReactNode
  className?: string
}

/** The dashboard layout: sidebar and content. */
export function AppShell({
  sidebar,
  header,
  children,
  className,
}: AppShellProps) {
  return (
    <div className={cn('min-h-screen bg-background', className)}>
      <div className="mx-auto flex min-h-screen w-full max-w-[1600px] gap-4 p-3 sm:p-4">
        {sidebar}
        <div className="flex min-w-0 flex-1 flex-col">
          {header}
          <main className="min-w-0 flex-1 px-2 pt-2 pb-6 sm:px-4">
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
