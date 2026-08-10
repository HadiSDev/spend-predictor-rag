import type { QueryClient, UseMutationOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import { entriesKey } from './entries'
import type {
  InvoiceLineCreate,
  InvoiceLineRead,
  InvoiceLineUpdate,
  InvoiceRead,
  InvoiceUpdate,
  InvoiceVerify,
  LineCorrections,
} from './types'

/**
 * Correct a parsed invoice header (`PATCH /invoices/{id}`).
 *
 * Accepted whatever the invoice's provenance — an ERP posting can be as wrong
 * as an extraction, and what keeps the correction from being erased by the next
 * sync is the server's per-field record of what a human settled.
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
 * Verify a parsed invoice header, optionally correcting it first
 * (`POST /invoices/{id}/verify`).
 *
 * Separate from the PATCH above because verifying is a different statement:
 * an empty body says "I read these values and they are right", which a
 * correction has no way to express — and it is that statement, not the
 * correction, that the extractor learns from.
 */
export function verifyInvoiceMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<InvoiceRead, Error, { id: string; body?: InvoiceVerify }> {
  return {
    mutationFn: ({ id, body }) =>
      api.post<InvoiceRead>(`/api/v1/invoices/${id}/verify`, body ?? {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/**
 * Correct what a line says was bought (`PATCH /invoice-lines/{id}`).
 *
 * Not the category — that is `verifyInvoiceLineMutation` below, which resolves
 * it against the company's tree. Sending one here is a 422 rather than a
 * silently dropped field.
 */
export function updateInvoiceLineMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<InvoiceLineRead, Error, { id: string; body: InvoiceLineUpdate }> {
  return {
    mutationFn: ({ id, body }) =>
      api.patch<InvoiceLineRead>(`/api/v1/invoice-lines/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/**
 * Add a line to an invoice (`POST /invoices/{id}/lines`).
 *
 * How a reviewer splits a stand-in line into what was actually bought: add the
 * real lines, then delete the stand-in. The invoice's reconciliation state
 * moves with each step, which is why this invalidates the whole family.
 */
export function createInvoiceLineMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<InvoiceLineRead, Error, { invoiceId: string; body: InvoiceLineCreate }> {
  return {
    mutationFn: ({ invoiceId, body }) =>
      api.post<InvoiceLineRead>(`/api/v1/invoices/${invoiceId}/lines`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/**
 * Delete a line (`DELETE /invoice-lines/{id}`).
 *
 * The line's values and its categorization are kept in the audit trail, and its
 * postings survive it with their line reference nulled — a posting is the
 * ledger's own evidence and is never deleted with a line.
 */
export function deleteInvoiceLineMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<void, Error, { id: string }> {
  return {
    mutationFn: ({ id }) => api.del<void>(`/api/v1/invoice-lines/${id}`),
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
