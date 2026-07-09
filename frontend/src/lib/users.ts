import { queryOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type { UserRead } from './types'

/** Query options for the current principal (`GET /users/me`). */
export function meQueryOptions(api: ApiClient) {
  return queryOptions({
    queryKey: ['users', 'me'],
    queryFn: () => api.get<UserRead>('/api/v1/users/me'),
    staleTime: 5 * 60 * 1000,
  })
}
