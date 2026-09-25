import { queryOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type { ErpTypeRead } from './types'

export const erpTypesKey = ['erp-types'] as const

/** The ERP systems this deployment can connect to (`GET /erp-types`), with the credential fields each one needs. */
export function erpTypesQueryOptions(api: ApiClient) {
  return queryOptions({
    queryKey: erpTypesKey,
    queryFn: () => api.get<Array<ErpTypeRead>>('/api/v1/erp-types'),
    staleTime: Infinity,
  })
}
