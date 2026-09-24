import { queryOptions } from '@tanstack/react-query'
import type { QueryClient, UseMutationOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type {
  ErpAccountRead,
  ErpAccountUpdate,
  RefreshAccountsResult,
} from './types'

/** Key prefix for an integration's chart of accounts. */
export function accountsKey(integrationId: string) {
  return ['erp-accounts', integrationId] as const
}

/** The integration's chart of accounts (`GET /erp-integrations/{id}/accounts`).
 *  Readable by any authenticated member; only writes are management-gated. */
export function accountsQueryOptions(
  api: ApiClient,
  integrationId: string | null,
) {
  return queryOptions({
    queryKey: accountsKey(integrationId ?? 'none'),
    queryFn: () =>
      api.get<Array<ErpAccountRead>>(
        `/api/v1/erp-integrations/${integrationId}/accounts`,
      ),
    enabled: integrationId !== null,
  })
}

/**
 * Toggle one account's settings (`PATCH /erp-accounts/{id}`).
 *
 * One request per account: a chart is reviewed by flipping a few switches, and
 * batching them behind a save button makes a partial failure impossible to
 * attribute to a row.
 *
 * The response *is* the updated account, so it is written straight into the
 * cached list rather than invalidating it. Invalidating refetched the whole
 * chart after every switch — tolerable for the debug ERP's 25 accounts, a
 * request storm for a real one: Billy's chart is 98, and "enable all" fired 98
 * PATCHes and 98 full GETs back to back.
 */
export function updateAccountMutation(
  api: ApiClient,
  queryClient: QueryClient,
  integrationId: string,
): UseMutationOptions<
  ErpAccountRead,
  Error,
  { id: string; body: ErpAccountUpdate }
> {
  return {
    mutationFn: ({ id, body }) =>
      api.patch<ErpAccountRead>(`/api/v1/erp-accounts/${id}`, body),
    onSuccess: (updated) => {
      queryClient.setQueryData<Array<ErpAccountRead>>(
        accountsKey(integrationId),
        // Left alone when the chart is not cached: there is no list to correct,
        // and seeding one from a single row would invent a chart of one.
        (previous) =>
          previous?.map((account) =>
            account.id === updated.id ? updated : account,
          ),
      )
    },
  }
}

/** Re-fetch the chart from the ERP. Customer settings survive it. */
export function refreshAccountsMutation(
  api: ApiClient,
  queryClient: QueryClient,
  integrationId: string,
): UseMutationOptions<RefreshAccountsResult, Error, void> {
  return {
    mutationFn: () =>
      api.post<RefreshAccountsResult>(
        `/api/v1/erp-integrations/${integrationId}/refresh-accounts`,
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: accountsKey(integrationId) }),
  }
}
