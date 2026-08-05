import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useClerk, useUser } from '@clerk/tanstack-react-start'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart3,
  ChevronDown,
  FileText,
  LayoutDashboard,
  LogOut,
  Moon,
  Settings,
  Sun,
  Users,
} from 'lucide-react'
import {
  AppShell,
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Card,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  IconButton,
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarNav,
  SidebarNavItem,
  Skeleton,
  Topbar,
  TopbarActions,
  TopbarTitle,
  useTheme,
} from '#/components/ui'
import { DashboardBody } from '#/components/dashboard/body'
import { usePrincipal, useApi } from '#/lib/auth'
import { entriesSummaryOptions, spendByCategoryOptions } from '#/lib/reports'

export const Route = createFileRoute('/_authed/')({ component: DashboardPage })

function initials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  moderator: 'Moderator',
  member: 'Member',
  viewer: 'Viewer',
}

function UserMenu() {
  const principal = usePrincipal()
  const { user } = useUser()
  const { signOut } = useClerk()
  const navigate = useNavigate()

  // Prefer Clerk's identity for display; fall back to the provisioned principal.
  const name = user?.fullName || user?.username || principal.name
  const email = user?.primaryEmailAddress?.emailAddress || principal.email
  const imageUrl = user?.hasImage ? user.imageUrl : undefined
  const roleLabel = principal.isSystemAdmin
    ? 'System admin'
    : (ROLE_LABELS[principal.role] ?? principal.role)

  async function handleSignOut() {
    await signOut()
    await navigate({ to: '/sign-in' })
  }

  const avatar = (className?: string) => (
    <Avatar className={className}>
      {imageUrl ? <AvatarImage src={imageUrl} alt={name} /> : null}
      <AvatarFallback>{initials(name)}</AvatarFallback>
    </Avatar>
  )

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            className="flex items-center gap-2 rounded-full py-1 pr-2 pl-1 outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
          >
            {avatar('size-8')}
            <span className="hidden max-w-36 truncate text-sm font-medium sm:block">{name}</span>
            <ChevronDown className="hidden size-4 text-muted-foreground sm:block" />
          </button>
        }
      />
      <DropdownMenuContent align="end" className="w-64">
        <div className="flex items-center gap-3 px-2 py-2">
          {avatar('size-10')}
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-foreground">{name}</div>
            <div className="truncate text-xs text-muted-foreground">{email}</div>
          </div>
        </div>
        <div className="px-2 pb-2">
          <Badge variant={principal.isSystemAdmin ? 'info' : 'outline'}>{roleLabel}</Badge>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleSignOut}>
          <LogOut />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function DashboardShell({ children }: { children: React.ReactNode }) {
  const { theme, toggleTheme } = useTheme()
  const principal = usePrincipal()

  return (
    <AppShell
      sidebar={
        <Sidebar>
          <SidebarHeader>
            <div className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
              <BarChart3 className="size-4" />
            </div>
            <span className="font-display text-lg font-semibold tracking-tight">Spend Predictor</span>
          </SidebarHeader>
          <SidebarContent>
            <SidebarNav>
              <SidebarNavItem icon={<LayoutDashboard />} active>
                Dashboard
              </SidebarNavItem>
              <SidebarNavItem icon={<FileText />} disabled>
                Invoices
              </SidebarNavItem>
              <SidebarNavItem icon={<Users />} disabled>
                Vendors
              </SidebarNavItem>
              <SidebarNavItem icon={<Settings />} disabled>
                Settings
              </SidebarNavItem>
            </SidebarNav>
          </SidebarContent>
        </Sidebar>
      }
      header={
        <Topbar>
          <TopbarTitle>Dashboard</TopbarTitle>
          <TopbarActions>
            <IconButton aria-label="Toggle theme" variant="outline" onClick={toggleTheme}>
              {theme === 'dark' ? <Sun /> : <Moon />}
            </IconButton>
            <UserMenu key={principal.id} />
          </TopbarActions>
        </Topbar>
      }
    >
      {children}
    </AppShell>
  )
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-card" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-card" />
    </div>
  )
}

function ErrorState() {
  return (
    <Card className="p-8 text-center">
      <h2 className="font-display text-base font-medium">Couldn’t load your dashboard</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        The reporting API request failed. Check that the web API is running and reachable, then
        reload the page.
      </p>
    </Card>
  )
}

function DashboardContent() {
  const api = useApi()
  const entries = useQuery(entriesSummaryOptions(api))
  const categories = useQuery(spendByCategoryOptions(api))

  if (entries.isPending || categories.isPending) return <LoadingState />
  if (entries.isError || categories.isError) return <ErrorState />

  return <DashboardBody entryRows={entries.data.rows} categoryRows={categories.data.rows} />
}

function DashboardPage() {
  return (
    <DashboardShell>
      <DashboardContent />
    </DashboardShell>
  )
}
