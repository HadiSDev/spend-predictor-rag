import * as React from 'react'
import { useAuth } from '@clerk/tanstack-react-start'
import { useQuery } from '@tanstack/react-query'
import { redirect } from '@tanstack/react-router'
import { LoadingScreen } from '#/components/ui'
import { createApiClient, type ApiClient } from './api-client'
import { meQueryOptions } from './users'
import type { UserRead } from './types'

/**
 * An authenticated web-API client bound to the current Clerk session. The token
 * is fetched per request via Clerk's `getToken` (Clerk caches it).
 */
export function useApi(): ApiClient {
  const { getToken } = useAuth()
  return React.useMemo(() => createApiClient(() => getToken()), [getToken])
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

/**
 * Loads `GET /users/me` and provides the principal to descendants. Renders a
 * loading fallback until it resolves and an error fallback if it fails, so
 * children can assume the principal exists.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const api = useApi()
  const meQuery = useQuery(meQueryOptions(api))

  if (meQuery.isPending) {
    return <LoadingScreen message="Loading your workspace…" />
  }
  if (meQuery.isError || !meQuery.data) {
    return (
      <div className="grid min-h-screen place-items-center bg-background px-6 text-center">
        <div className="max-w-sm">
          <h1 className="font-display text-lg font-semibold">Couldn’t load your account</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Something went wrong loading your profile. Please try again.
          </p>
        </div>
      </div>
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

/**
 * Guard foundation for future `/admin/*` routes: throws a redirect to the
 * dashboard when the principal is not a platform system admin. No admin route
 * uses it yet.
 */
export function requireSystemAdmin(principal: Principal): void {
  if (!principal.isSystemAdmin) {
    throw redirect({ to: '/' })
  }
}
