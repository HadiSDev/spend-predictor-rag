import * as React from 'react'
import { useAuth, useClerk } from '@clerk/tanstack-react-start'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { redirect } from '@tanstack/react-router'
import { Button, LoadingScreen } from '#/components/ui'
import { ApiError, createApiClient } from '#/lib/api/api-client'
import type { ApiClient } from '#/lib/api/api-client'
import { meQueryOptions } from '#/lib/api/users'
import type { UserRead } from '#/lib/api/types'

/** An authenticated web-API client bound to the current Clerk session. */
export function useApi(): ApiClient {
  const { getToken } = useAuth()
  return React.useMemo(
    () => createApiClient((options) => getToken(options)),
    [getToken],
  )
}

/** The current principal, shaped for the UI. */
export interface Principal {
  id: string
  email: string
  name: string
  role: string
  isSystemAdmin: boolean
  organizationId: string
}

function toPrincipal(u: UserRead): Principal {
  return {
    id: u.id,
    email: u.email,
    name: u.name,
    role: u.role,
    isSystemAdmin: u.is_system_admin,
    organizationId: u.organization_id,
  }
}

const PrincipalContext = React.createContext<Principal | null>(null)

/** Clears cached web-API results when the active organization changes. */
function OrgScope({ children }: { children: React.ReactNode }) {
  const { orgId } = useAuth()
  const queryClient = useQueryClient()
  const [scopedOrgId, setScopedOrgId] = React.useState(orgId)

  React.useLayoutEffect(() => {
    if (scopedOrgId === orgId) {
      return
    }
    queryClient.clear()
    setScopedOrgId(orgId)
  }, [orgId, scopedOrgId, queryClient])

  if (scopedOrgId !== orgId) {
    return <LoadingScreen message="Switching organization…" />
  }

  return <React.Fragment key={orgId ?? 'no-org'}>{children}</React.Fragment>
}

/** Loads `GET /users/me` and provides the principal to descendants. */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  return (
    <OrgScope>
      <PrincipalProvider>{children}</PrincipalProvider>
    </OrgScope>
  )
}

/** Whether a failure means the caller's organization is suspended. */
export function isSuspendedOrgError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 403 &&
    /suspend/i.test(error.detail)
  )
}

function Notice({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="grid min-h-screen place-items-center bg-background px-6 text-center">
      <div className="max-w-sm">
        <h1 className="font-display text-lg font-semibold">{title}</h1>
        {children}
      </div>
    </div>
  )
}

function SuspendedScreen() {
  const { signOut } = useClerk()
  return (
    <Notice title="Organization suspended">
      <p className="mt-2 text-sm text-muted-foreground">
        This organization has been suspended. Its data is retained, but access
        stays blocked until it is restored. Contact an administrator if you
        think this is a mistake.
      </p>
      <Button
        className="mt-6"
        variant="secondary"
        onClick={() => void signOut({ redirectUrl: '/sign-in' })}
      >
        Sign out
      </Button>
    </Notice>
  )
}

function PrincipalProvider({ children }: { children: React.ReactNode }) {
  const api = useApi()
  const meQuery = useQuery(meQueryOptions(api))

  if (meQuery.isPending) {
    return <LoadingScreen message="Loading your workspace…" />
  }
  if (isSuspendedOrgError(meQuery.error)) {
    return <SuspendedScreen />
  }
  if (meQuery.isError) {
    return (
      <Notice title="Couldn’t load your account">
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong loading your profile. Please try again.
        </p>
        <Button
          className="mt-6"
          variant="secondary"
          onClick={() => void meQuery.refetch()}
        >
          Try again
        </Button>
      </Notice>
    )
  }

  return (
    <PrincipalContext.Provider value={toPrincipal(meQuery.data)}>
      {children}
    </PrincipalContext.Provider>
  )
}

/** The current principal. Must be used under an `AuthProvider`. */
export function usePrincipal(): Principal {
  const principal = React.useContext(PrincipalContext)
  if (!principal) {
    throw new Error('usePrincipal must be used within an <AuthProvider>')
  }
  return principal
}

/** Role gates for management UI. */

/** May edit the organization profile and reach the danger zone. */
export function canManageOrganization(principal: Principal): boolean {
  return principal.isSystemAdmin || principal.role === 'admin'
}

/** May create, edit, and (de)activate companies. */
export function canManageCompanies(principal: Principal): boolean {
  return (
    principal.isSystemAdmin ||
    principal.role === 'admin' ||
    principal.role === 'moderator'
  )
}

/** Redirects to the dashboard unless the principal is a system admin. */
export function requireSystemAdmin(principal: Principal): void {
  if (!principal.isSystemAdmin) {
    throw redirect({ to: '/' })
  }
}
