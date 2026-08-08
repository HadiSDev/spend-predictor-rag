import { queryOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type { EntryFilters, ErpEntryRead, Page, VoucherGroupRead } from './types'

/** Key prefix for every entry query, so one invalidation covers them all. */
export const entriesKey = ['erp-entries'] as const

/**
 * Voucher groups (`GET /erp-entries/vouchers`). Pagination is over vouchers,
 * so a voucher's postings always arrive together.
 *
 * The filter object is the cache key, which means each filter combination is
 * cached independently and going back to a previous filter is instant.
 */
export function voucherGroupsQueryOptions(api: ApiClient, filters: EntryFilters = {}) {
  // Base mode is asked for rather than assumed: the whole table formats in the
  // company's currency, so a server-side default change must not silently
  // relabel every figure.
  const query = { currency_mode: 'base' as const, ...filters }
  return queryOptions({
    queryKey: [...entriesKey, 'vouchers', query],
    queryFn: () => api.get<Page<VoucherGroupRead>>('/api/v1/erp-entries/vouchers', query),
  })
}

/** One posting's full detail (`GET /erp-entries/{id}`). */
export function entryQueryOptions(api: ApiClient, id: string | null) {
  return queryOptions({
    queryKey: [...entriesKey, 'detail', id],
    queryFn: () => api.get<ErpEntryRead>(`/api/v1/erp-entries/${id}`),
    enabled: id !== null,
  })
}
