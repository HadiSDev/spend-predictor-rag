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

/** How a voucher is addressed: by its id, or by one of its postings when it
 *  has none (an unlinked entry forms a voucher group of one — see
 *  `web_api/routers/erp_entries.py`). A voucher id, when present, wins. */
export type VoucherKey = { voucher?: string; entry?: string }

/**
 * A request to open the panel: which voucher, and — when the row that was
 * activated says so — which face of it to open on.
 *
 * `tab` lives on the selection rather than on `VoucherKey` because it is not
 * part of a voucher's identity: it queries nothing. It is declared here, in one
 * place, because it previously was not: the table asked for `tab: 'lines'`
 * through a callback typed to accept only a `VoucherKey`, which TypeScript
 * accepts and the route then silently dropped.
 */
export type VoucherSelection = VoucherKey & {
  tab?: VoucherTab
  /**
   * The line the reader activated, when they activated one.
   *
   * Deliberately **not** carried in the URL, unlike `voucher`/`entry`/`tab`:
   * paging is a position within an open panel, and writing it to the URL would
   * put a history entry behind every step, so Back would walk through lines
   * instead of leaving the panel. It seeds the panel and the panel owns it.
   */
  line?: string
}

/** The path segment for a key, or null when nothing is selected — the caller
 *  turns that into `enabled: false` rather than firing a request. */
function voucherPath(key: VoucherKey): string | null {
  if (key.voucher) return `/api/v1/erp-entries/vouchers/${encodeURIComponent(key.voucher)}`
  if (key.entry) return `/api/v1/erp-entries/vouchers/by-entry/${encodeURIComponent(key.entry)}`
  return null
}

/**
 * One voucher's postings, invoice and document in a single request
 * (`GET /erp-entries/vouchers/{id}` or `.../by-entry/{id}`).
 *
 * The query is keyed on the raw `voucher`/`entry` values rather than the
 * derived path, so switching between two vouchers is two distinct cache
 * entries even though both resolve through the same endpoint shape.
 */
export function voucherDetailQueryOptions(api: ApiClient, key: VoucherKey) {
  const path = voucherPath(key)
  // Base mode is asked for rather than assumed — same reasoning as
  // `voucherGroupsQueryOptions`: the drawer's header renders `amount`/
  // `currency` straight from this payload, in the company's currency, so a
  // server-side default change must not silently relabel the figure it shows
  // (or make it disagree with the table row the drawer was opened from).
  const query = { currency_mode: 'base' as const }
  return queryOptions({
    queryKey: [...entriesKey, 'voucher', key.voucher ?? null, key.entry ?? null],
    // `path` is only null when the query is disabled below, so TanStack Query
    // never actually calls this — the throw is a loud guard against that
    // invariant breaking, not a path this app is meant to take.
    queryFn: () => {
      if (path === null) throw new Error('voucherDetailQueryOptions: no voucher or entry id given')
      return api.get<VoucherDetailRead>(path, query)
    },
    enabled: path !== null,
  })
}

/** The voucher's change history, newest first (`.../audit` sibling of the
 *  detail route above). */
export function voucherAuditQueryOptions(api: ApiClient, key: VoucherKey) {
  const path = voucherPath(key)
  return queryOptions({
    queryKey: [...entriesKey, 'voucher-audit', key.voucher ?? null, key.entry ?? null],
    queryFn: () => {
      if (path === null) throw new Error('voucherAuditQueryOptions: no voucher or entry id given')
      return api.get<Array<VoucherAuditRead>>(`${path}/audit`)
    },
    enabled: path !== null,
  })
}

/**
 * The invoice's PDF as a Blob, fetched through the API client rather than
 * given to an `<iframe src>` — the route needs the Clerk bearer token, which
 * only the client attaches.
 *
 * `staleTime: Infinity`: the document is immutable (it's the scanned
 * original), so refetching it would only re-hit the ERP for bytes that
 * cannot have changed. `retry: false`: a failed fetch should surface to the
 * user with a retry affordance, not retry silently in the background.
 */
export function invoiceDocumentQueryOptions(api: ApiClient, invoiceId: string | null) {
  return queryOptions({
    queryKey: [...entriesKey, 'document', invoiceId],
    queryFn: () => {
      if (invoiceId === null) throw new Error('invoiceDocumentQueryOptions: no invoice id given')
      return api.getBlob(`/api/v1/invoices/${invoiceId}/document`)
    },
    enabled: invoiceId !== null,
    staleTime: Infinity,
    retry: false,
  })
}
