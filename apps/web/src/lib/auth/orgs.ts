import * as React from 'react'
import { useOrganizationList } from '@clerk/tanstack-react-start'

/** Membership listing params shared by the auth gate and the org switcher. */
export const membershipListParams = {
  userMemberships: { pageSize: 50 },
} as const

export interface OrgMembership {
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

  return {
    isLoaded: orgList.isLoaded,
    memberships,
    setActive: orgList.setActive,
  }
}
