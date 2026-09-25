import { queryOptions } from '@tanstack/react-query'
import type { QueryClient, UseMutationOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type {
  ErpIntegrationCreate,
  ErpIntegrationRead,
  ErpIntegrationReplace,
  ErpIntegrationUpdate,
} from './types'

/** Key prefix for every integration list. */
export const integrationsKey = ['erp-integrations'] as const

/** The ERP integrations of every company in scope (`GET /erp-integrations`). */
export function integrationsQueryOptions(api: ApiClient) {
  return queryOptions({
    queryKey: integrationsKey,
    queryFn: () =>
      api.get<Array<ErpIntegrationRead>>('/api/v1/erp-integrations'),
  })
}

function invalidateIntegrations(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: integrationsKey })
}

/** Connect an ERP to an existing company (`POST /erp-integrations`). */
export function connectIntegrationMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<ErpIntegrationRead, Error, ErpIntegrationCreate> {
  return {
    mutationFn: (body) =>
      api.post<ErpIntegrationRead>('/api/v1/erp-integrations', body),
    onSuccess: () => invalidateIntegrations(queryClient),
  }
}

/** Update an integration (`PATCH /erp-integrations/{id}`). */
export function updateIntegrationMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<
  ErpIntegrationRead,
  Error,
  { id: string; body: ErpIntegrationUpdate }
> {
  return {
    mutationFn: ({ id, body }) =>
      api.patch<ErpIntegrationRead>(`/api/v1/erp-integrations/${id}`, body),
    onSuccess: () => invalidateIntegrations(queryClient),
  }
}

/** Move a company to a different ERP (`POST /erp-integrations/{id}/replace`). */
export function replaceIntegrationMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<
  ErpIntegrationRead,
  Error,
  { id: string; body: ErpIntegrationReplace }
> {
  return {
    mutationFn: ({ id, body }) =>
      api.post<ErpIntegrationRead>(
        `/api/v1/erp-integrations/${id}/replace`,
        body,
      ),
    onSuccess: () => invalidateIntegrations(queryClient),
  }
}
