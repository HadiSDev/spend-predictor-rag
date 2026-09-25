import { queryOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type { Page, VendorRead } from './types'

/** The org's suppliers (`GET /vendors`). */
export function vendorsQueryOptions(
  api: ApiClient,
  { q }: { q?: string } = {},
) {
  return queryOptions({
    queryKey: ['vendors', { q: q || undefined }],
    queryFn: () =>
      api.get<Page<VendorRead>>('/api/v1/vendors', { q: q || undefined }),
  })
}
