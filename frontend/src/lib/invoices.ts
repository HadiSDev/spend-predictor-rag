import type { QueryClient, UseMutationOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import { entriesKey } from './entries'
import type { InvoiceLineRead, InvoiceRead, InvoiceUpdate, LineCorrections } from './types'

/**
 * Correct an AI-parsed invoice header (`PATCH /invoices/{id}`). 409s for an
 * `erp`-sourced invoice — the UI never offers the action for one, but a
 * caller that hits the endpoint anyway still needs the rejection to surface
 * rather than being swallowed.
 *
 * Invalidates the whole `entriesKey` family, not just this invoice: the
 * voucher detail panel, its audit feed, and the groups list all embed the
 * header this just changed.
 */
export function updateInvoiceMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<InvoiceRead, Error, { id: string; body: InvoiceUpdate }> {
  return {
    mutationFn: ({ id, body }) => api.patch<InvoiceRead>(`/api/v1/invoices/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/**
 * Queue an invoice's document to be read again (`POST /invoices/{id}/reprocess`).
 *
 * The same `entriesKey` invalidation as the others, and for a stronger reason:
 * a successful extraction *replaces* the invoice's lines, so the voucher's rows
 * in the table, the panel's Lines tab and the audit feed are all stale
 * afterwards. Invalidating the whole prefix is what makes the panel reflect the
 * new state without a manual reload.
 */
export function reprocessInvoiceMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<InvoiceRead, Error, { id: string }> {
  return {
    mutationFn: ({ id }) => api.post<InvoiceRead>(`/api/v1/invoices/${id}/reprocess`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/**
 * Verify a line's categorization, optionally correcting it
 * (`POST /invoice-lines/{id}/verify`). Marks the line `verified` and
 * recomputes the invoice's status rollup server-side, so the same
 * `entriesKey` invalidation as the header update applies — the voucher
 * detail, the audit feed, and the groups list (which shows the rollup) all
 * refresh.
 */
export function verifyInvoiceLineMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<InvoiceLineRead, Error, { id: string; corrections: LineCorrections }> {
  return {
    mutationFn: ({ id, corrections }) =>
      api.post<InvoiceLineRead>(`/api/v1/invoice-lines/${id}/verify`, corrections),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}
