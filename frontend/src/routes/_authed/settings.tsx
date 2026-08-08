import { Link, Outlet, createFileRoute, useRouterState } from '@tanstack/react-router'
import { Tabs, TabsList, TabsTab } from '#/components/ui'

export const Route = createFileRoute('/_authed/settings')({
  component: SettingsLayout,
  staticData: { title: 'Settings' },
})

/** The sections, in tab order. Each is a child route, so it is linkable. */
const TABS = [
  { to: '/settings/profile', label: 'Profile' },
  { to: '/settings/organization', label: 'Organization' },
  { to: '/settings/companies', label: 'Companies' },
] as const

function SettingsLayout() {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  // Derived from the route, never held in state: the URL is the source of truth
  // so a reload or a back navigation lands on the same section.
  const active = TABS.find((tab) => pathname.startsWith(tab.to))?.to ?? TABS[0].to

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your profile, your organization, and the companies it reports on.
        </p>
      </div>

      <Tabs value={active}>
        <TabsList>
          {TABS.map((tab) => (
            <TabsTab key={tab.to} value={tab.to} render={<Link to={tab.to} />}>
              {tab.label}
            </TabsTab>
          ))}
        </TabsList>
      </Tabs>

      <Outlet />
    </div>
  )
}
