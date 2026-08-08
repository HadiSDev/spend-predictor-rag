import { queryOptions } from '@tanstack/react-query'
import type { QueryClient, UseMutationOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type {
  CompanyCreate,
  CompanyCreateResult,
  CompanyRead,
  CompanyUpdate,
  FxRecomputeResult,
} from './types'

/** Key prefix for every company list. Invalidating it refreshes both the
 * active-only and the include-inactive caches. */
export const companiesKey = ['companies'] as const

/** The organization's companies (`GET /companies`). */
export function companiesQueryOptions(
  api: ApiClient,
  { includeInactive = false }: { includeInactive?: boolean } = {},
) {
  return queryOptions({
    queryKey: [...companiesKey, { includeInactive }],
    queryFn: () =>
      api.get<Array<CompanyRead>>('/api/v1/companies', { include_inactive: includeInactive }),
  })
}

function invalidateCompanies(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: companiesKey })
}

/**
 * Create a company together with its ERP integration (`POST /companies`). The
 * two are one request, so a company is never left without a connection.
 */
export function createCompanyMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<CompanyCreateResult, Error, CompanyCreate> {
  return {
    mutationFn: (body) => api.post<CompanyCreateResult>('/api/v1/companies', body),
    onSuccess: () => invalidateCompanies(queryClient),
  }
}

/** Partially update a company (`PATCH /companies/{id}`). */
export function updateCompanyMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<CompanyRead, Error, { id: string; body: CompanyUpdate }> {
  return {
    mutationFn: ({ id, body }) => api.patch<CompanyRead>(`/api/v1/companies/${id}`, body),
    onSuccess: () => invalidateCompanies(queryClient),
  }
}

/**
 * Deactivate or reactivate a company. Companies are soft-deactivated and never
 * hard-deleted, so there is no delete mutation to offer.
 */
export function setCompanyActiveMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<CompanyRead, Error, { id: string; active: boolean }> {
  return {
    mutationFn: ({ id, active }) =>
      api.post<CompanyRead>(`/api/v1/companies/${id}/${active ? 'activate' : 'deactivate'}`),
    onSuccess: () => invalidateCompanies(queryClient),
  }
}

/**
 * Rewrite a company's stored figures into its current base currency
 * (`POST /companies/{id}/recompute-fx`).
 *
 * Separate from the PATCH that changes the currency on purpose: rewriting a
 * year of postings is not something to do inside a settings save. Each row is
 * reconverted at its *own* historical rate, so this restates nothing at today's.
 */
export function recomputeCompanyFxMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<FxRecomputeResult, Error, { id: string }> {
  return {
    mutationFn: ({ id }) =>
      api.post<FxRecomputeResult>(`/api/v1/companies/${id}/recompute-fx`),
    // Every amount in the app may have just changed.
    onSuccess: () => queryClient.invalidateQueries(),
  }
}
