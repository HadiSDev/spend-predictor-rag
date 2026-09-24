import { queryOptions } from '@tanstack/react-query'
import type { QueryClient, UseMutationOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type { OrganizationRead, OrganizationUpdate } from './types'

/** Query key for the organization profile. */
export const organizationKey = ['organization'] as const

/** Query key for the current principal — re-read whenever the caller's own
 * role or organization may have changed. */
export const meKey = ['users', 'me'] as const

/** The caller's organization profile (`GET /organization`). */
export function organizationQueryOptions(api: ApiClient) {
  return queryOptions({
    queryKey: organizationKey,
    queryFn: () => api.get<OrganizationRead>('/api/v1/organization'),
  })
}

/**
 * Update the organization profile (`PATCH /organization`). Invalidate rather
 * than patch the cache optimistically: the server normalizes what it stores.
 */
export function updateOrganizationMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<OrganizationRead, Error, OrganizationUpdate> {
  return {
    mutationFn: (body) => api.patch<OrganizationRead>('/api/v1/organization', body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: organizationKey }),
        queryClient.invalidateQueries({ queryKey: meKey }),
      ])
    },
  }
}

/**
 * Soft-suspend the organization (`DELETE /organization`). Data is retained and
 * the suspension propagates to Clerk; every later API call then returns 403
 * "Organization is suspended". Clearing the cache lets the app converge on the
 * suspended screen in `AuthProvider` rather than scripting a bespoke exit.
 */
export function suspendOrganizationMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<OrganizationRead, Error, void> {
  return {
    mutationFn: () => api.del<OrganizationRead>('/api/v1/organization'),
    onSuccess: () => {
      queryClient.clear()
    },
  }
}
