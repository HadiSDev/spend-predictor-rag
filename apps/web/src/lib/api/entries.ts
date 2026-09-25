import { queryOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type {
  EntryFilters,
  ErpEntryRead,
  Page,
  VoucherAuditRead,
  VoucherDetailRead,
  VoucherGroupRead,
  VoucherTab,
} from './types'

/** Key prefix for every entry query. */
export const entriesKey = ['erp-entries'] as const

/** Voucher groups (`GET /erp-entries/vouchers`). */
export function voucherGroupsQueryOptions(
  api: ApiClient,
  filters: EntryFilters = {},
) {
  const query = { currency_mode: 'base' as const, ...filters }
  return queryOptions({
    queryKey: [...entriesKey, 'vouchers', query],
    queryFn: () =>
      api.get<Page<VoucherGroupRead>>('/api/v1/erp-entries/vouchers', query),
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

/** How a voucher is addressed: by its id, or by one of its postings. */
export type VoucherKey = { voucher?: string; entry?: string }

/** A request to open the voucher panel, optionally on a given face. */
export type VoucherSelection = VoucherKey & {
  tab?: VoucherTab
  /** The line the reader activated, when they activated one. */
  line?: string
}

/** The path segment for a key, or null when nothing is selected. */
function voucherPath(key: VoucherKey): string | null {
  if (key.voucher) {
    return `/api/v1/erp-entries/vouchers/${encodeURIComponent(key.voucher)}`
  }
  if (key.entry) {
    return `/api/v1/erp-entries/vouchers/by-entry/${encodeURIComponent(key.entry)}`
  }
  return null
}

/** One voucher's postings, invoice and document in a single request (`GET /erp-entries/vouchers/{id}` or `.../by-entry/{id}`). */
export function voucherDetailQueryOptions(api: ApiClient, key: VoucherKey) {
  const path = voucherPath(key)
  const query = { currency_mode: 'base' as const }
  return queryOptions({
    queryKey: [
      ...entriesKey,
      'voucher',
      key.voucher ?? null,
      key.entry ?? null,
    ],
    queryFn: () => {
      if (path === null) {
        throw new Error(
          'voucherDetailQueryOptions: no voucher or entry id given',
        )
      }
      return api.get<VoucherDetailRead>(path, query)
    },
    enabled: path !== null,
  })
}

/** The voucher's change history, newest first. */
export function voucherAuditQueryOptions(api: ApiClient, key: VoucherKey) {
  const path = voucherPath(key)
  return queryOptions({
    queryKey: [
      ...entriesKey,
      'voucher-audit',
      key.voucher ?? null,
      key.entry ?? null,
    ],
    queryFn: () => {
      if (path === null) {
        throw new Error(
          'voucherAuditQueryOptions: no voucher or entry id given',
        )
      }
      return api.get<Array<VoucherAuditRead>>(`${path}/audit`)
    },
    enabled: path !== null,
  })
}

/** The invoice's PDF as a Blob. */
export function invoiceDocumentQueryOptions(
  api: ApiClient,
  invoiceId: string | null,
) {
  return queryOptions({
    queryKey: [...entriesKey, 'document', invoiceId],
    queryFn: () => {
      if (invoiceId === null) {
        throw new Error('invoiceDocumentQueryOptions: no invoice id given')
      }
      return api.getBlob(`/api/v1/invoices/${invoiceId}/document`)
    },
    enabled: invoiceId !== null,
    staleTime: Infinity,
    retry: false,
  })
}
