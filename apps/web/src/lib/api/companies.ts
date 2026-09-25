import { queryOptions } from '@tanstack/react-query'
import type { QueryClient, UseMutationOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type {
  CompanyCreate,
  CompanyCreateResult,
  CompanyDeleteResult,
  CompanyRead,
  CompanyUpdate,
  CompanyUpdateResult,
  FxRecomputeResult,
  RecategorizeResult,
} from './types'

/** Key prefix for every company list. */
export const companiesKey = ['companies'] as const

/** The organization's companies (`GET /companies`). */
export function companiesQueryOptions(
  api: ApiClient,
  { includeInactive = false }: { includeInactive?: boolean } = {},
) {
  return queryOptions({
    queryKey: [...companiesKey, { includeInactive }],
    queryFn: () =>
      api.get<Array<CompanyRead>>('/api/v1/companies', {
        include_inactive: includeInactive,
      }),
  })
}

function invalidateCompanies(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: companiesKey })
}

/** Create a company together with its ERP integration (`POST /companies`). */
export function createCompanyMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<CompanyCreateResult, Error, CompanyCreate> {
  return {
    mutationFn: (body) =>
      api.post<CompanyCreateResult>('/api/v1/companies', body),
    onSuccess: () => invalidateCompanies(queryClient),
  }
}

/** Partially update a company (`PATCH /companies/{id}`). */
export function updateCompanyMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<
  CompanyUpdateResult,
  Error,
  { id: string; body: CompanyUpdate }
> {
  return {
    mutationFn: ({ id, body }) =>
      api.patch<CompanyUpdateResult>(`/api/v1/companies/${id}`, body),
    onSuccess: () => {
      invalidateCompanies(queryClient)
      void queryClient.invalidateQueries({ queryKey: ['erp-entries'] })
      void queryClient.invalidateQueries({ queryKey: ['invoice-lines'] })
    },
  }
}

/** Deactivate or reactivate a company. */
export function setCompanyActiveMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<CompanyRead, Error, { id: string; active: boolean }> {
  return {
    mutationFn: ({ id, active }) =>
      api.post<CompanyRead>(
        `/api/v1/companies/${id}/${active ? 'activate' : 'deactivate'}`,
      ),
    onSuccess: () => invalidateCompanies(queryClient),
  }
}

/** Destroy a company and everything it owns (`DELETE /companies/{id}`). */
export function deleteCompanyMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<
  CompanyDeleteResult,
  Error,
  { id: string; confirm?: boolean }
> {
  return {
    mutationFn: ({ id, confirm }) =>
      api.del<CompanyDeleteResult>(`/api/v1/companies/${id}`, { confirm }),
    onSuccess: () => queryClient.invalidateQueries(),
  }
}

/** Rewrite a company's stored figures into its current base currency (`POST /companies/{id}/recompute-fx`). */
export function recomputeCompanyFxMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<FxRecomputeResult, Error, { id: string }> {
  return {
    mutationFn: ({ id }) =>
      api.post<FxRecomputeResult>(`/api/v1/companies/${id}/recompute-fx`),
    onSuccess: () => queryClient.invalidateQueries(),
  }
}

/** Put a company's failed lines back in the categorizer's queue (`POST /companies/{id}/recategorize`). */
export function recategorizeCompanyMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<RecategorizeResult, Error, { id: string }> {
  return {
    mutationFn: ({ id }) =>
      api.post<RecategorizeResult>(`/api/v1/companies/${id}/recategorize`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['erp-entries'] }),
  }
}
