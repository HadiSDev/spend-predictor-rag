import * as React from 'react'
import { Outlet, createFileRoute, useNavigate } from '@tanstack/react-router'
import { useAuth, useOrganizationList } from '@clerk/tanstack-react-start'
import { LoadingScreen } from '#/components/ui'
import { AuthProvider } from '#/lib/auth'

export const Route = createFileRoute('/_authed')({ component: AuthedLayout })

function FullScreen({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen place-items-center bg-background px-6 text-center text-muted-foreground">
      <div>{children}</div>
    </div>
  )
}

/**
 * Client-side auth gate. Clerk's client SDK is authoritative about the session
 * (and handles the dev handshake), so we gate here rather than with a server
 * `auth()` in `beforeLoad`. `treatPendingAsSignedOut: false` lets us see a
 * "pending" session (signed in but no active organization) and resolve its org
 * task ourselves instead of bouncing back to sign-in.
 */
function AuthedLayout() {
  const { isLoaded, isSignedIn, orgId } = useAuth({ treatPendingAsSignedOut: false })
  const navigate = useNavigate()
  const orgList = useOrganizationList({ userMemberships: true })
  const memberships = orgList.userMemberships?.data
  const activating = React.useRef(false)

  // Truly signed out → sign-in.
  React.useEffect(() => {
    if (isLoaded && !isSignedIn) void navigate({ to: '/sign-in' })
  }, [isLoaded, isSignedIn, navigate])

  // Signed in but no active org (pending org task) → activate the first
  // membership once. This resolves the pending session into an active one.
  React.useEffect(() => {
    if (!isSignedIn || orgId || activating.current) return
    if (!orgList.isLoaded || !orgList.setActive) return
    const first = memberships?.[0]
    if (first) {
      activating.current = true
      void orgList.setActive({ organization: first.organization.id })
    }
  }, [isSignedIn, orgId, orgList.isLoaded, orgList.setActive, memberships])

  if (!isLoaded) return <LoadingScreen />
  if (!isSignedIn) return <LoadingScreen message="Redirecting…" />

  // Pending: signed in but no active organization yet.
  if (!orgId) {
    if (orgList.isLoaded && memberships && memberships.length === 0) {
      return (
        <FullScreen>
          <h1 className="font-display text-lg font-semibold text-foreground">No organization</h1>
          <p className="mx-auto mt-2 max-w-sm text-sm">
            Your account isn’t a member of any organization yet. Ask an administrator to invite you
            (or create one in Clerk), then reload.
          </p>
        </FullScreen>
      )
    }
    return <LoadingScreen message="Preparing your workspace…" />
  }

  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  )
}
