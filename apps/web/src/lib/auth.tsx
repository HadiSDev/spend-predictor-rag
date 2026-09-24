import * as React from 'react'
import { useAuth, useClerk } from '@clerk/tanstack-react-start'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { redirect } from '@tanstack/react-router'
import { Button, LoadingScreen } from '#/components/ui'
import { ApiError, createApiClient } from './api-client'
import type { ApiClient } from './api-client'
import { meQueryOptions } from './users'
import type { UserRead } from './types'

/**
 * An authenticated web-API client bound to the current Clerk session. The
 * token is fetched per request via Clerk's `getToken`, which normally serves
 * a cached token; `api-client.ts`'s retry-on-401 seam calls back in with
 * `{ skipCache: true }` to mint a fresh one after a stale cached token is
 * rejected (e.g. a tab left idle past the session token's short lifetime).
 * This is the one place that knows the token getter is backed by Clerk —
 * `api-client.ts` itself stays framework-agnostic and never imports Clerk.
 */
export function useApi(): ApiClient {
  const { getToken } = useAuth()
  return React.useMemo(() => createApiClient((options) => getToken(options)), [getToken])
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
 * Discards every cached web-API result when the active organization changes,
 * and keeps children unmounted until it has.
 *
 * All cached data is tenant-scoped, so nothing survives a switch: the cache is
 * cleared wholesale rather than threading `orgId` through every query key.
 * Unmounting children while that happens is what makes it airtight — a request
 * issued with the previous token can resolve after the clear, and with no
 * mounted observers it has nowhere to land.
 *
 * Keyed on the observed `orgId` rather than on the switcher's click handler, so
 * it also covers switches from Clerk's own flows, another tab, or the
 * pending-org activation in `_authed.tsx`.
 */
function OrgScope({ children }: { children: React.ReactNode }) {
  const { orgId } = useAuth()
  const queryClient = useQueryClient()
  // The organization whose data the cache currently holds.
  const [scopedOrgId, setScopedOrgId] = React.useState(orgId)

  React.useLayoutEffect(() => {
    if (scopedOrgId === orgId) return
    queryClient.clear()
    setScopedOrgId(orgId)
  }, [orgId, scopedOrgId, queryClient])

  if (scopedOrgId !== orgId) {
    return <LoadingScreen message="Switching organization…" />
  }

  return <React.Fragment key={orgId ?? 'no-org'}>{children}</React.Fragment>
}

/**
 * Loads `GET /users/me` and provides the principal to descendants. Renders a
 * loading fallback until it resolves and an error fallback if it fails, so
 * children can assume the principal exists.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  return (
    <OrgScope>
      <PrincipalProvider>{children}</PrincipalProvider>
    </OrgScope>
  )
}

/**
 * Whether a failure is the web API refusing every request because the caller's
 * organization is suspended. `web_api/deps.py` raises 403 "Organization is
 * suspended" from `current_user`, so it surfaces on `/users/me` first — whether
 * the org was suspended from our own danger zone, from Clerk, or by an admin in
 * another session.
 */
export function isSuspendedOrgError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403 && /suspend/i.test(error.detail)
}

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
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
        This organization has been suspended. Its data is retained, but access stays blocked until
        it is restored. Contact an administrator if you think this is a mistake.
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
        <Button className="mt-6" variant="secondary" onClick={() => void meQuery.refetch()}>
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

/**
 * Role gates for management UI. These mirror the authorization dependencies in
 * `apps/web-api/src/web_api/deps.py` — `require_org_admin` for the organization profile and
 * `require_management` for company writes. Keep them in step with that file:
 * they are a usability affordance so unauthorized users see read-only views
 * instead of controls that fail on submit, never the enforcement point. Every
 * mutation still renders a server 403 as an error.
 */

/** May edit the organization profile and reach the danger zone. */
export function canManageOrganization(principal: Principal): boolean {
  return principal.isSystemAdmin || principal.role === 'admin'
}

/** May create, edit, and (de)activate companies. */
export function canManageCompanies(principal: Principal): boolean {
  return (
    principal.isSystemAdmin || principal.role === 'admin' || principal.role === 'moderator'
  )
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
