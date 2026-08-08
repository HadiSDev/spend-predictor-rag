import * as React from 'react'
import { useOrganizationList } from '@clerk/tanstack-react-start'

/**
 * One listing shape for the signed-in user's organization memberships, shared by
 * the auth gate (which activates a pending session's first membership) and the
 * org switcher — so Clerk serves both from a single request.
 *
 * The page size is the ceiling on how many organizations the switcher shows;
 * beyond it, infinite loading would have to be wired in here.
 */
export const membershipListParams = { userMemberships: { pageSize: 50 } } as const

export interface OrgMembership {
  /** Clerk organization id — what `setActive` expects. */
  id: string
  name: string
}

/** The user's organization memberships, by name, plus Clerk's activator. */
export function useOrgMemberships() {
  const orgList = useOrganizationList(membershipListParams)
  const data = orgList.userMemberships.data

  const memberships: Array<OrgMembership> = React.useMemo(
    () =>
      (data ?? [])
        .map((m) => ({ id: m.organization.id, name: m.organization.name }))
        .sort((a, b) => a.name.localeCompare(b.name)),
    [data],
  )

  return { isLoaded: orgList.isLoaded, memberships, setActive: orgList.setActive }
}
