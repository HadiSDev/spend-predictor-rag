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

/** Correct a parsed invoice header (`PATCH /invoices/{id}`). */
export function updateInvoiceMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<InvoiceRead, Error, { id: string; body: InvoiceUpdate }> {
  return {
    mutationFn: ({ id, body }) =>
      api.patch<InvoiceRead>(`/api/v1/invoices/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/** Verify a parsed invoice header, optionally correcting it first (`POST /invoices/{id}/verify`). */
export function verifyInvoiceMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<
  InvoiceRead,
  Error,
  { id: string; body?: InvoiceVerify }
> {
  return {
    mutationFn: ({ id, body }) =>
      api.post<InvoiceRead>(`/api/v1/invoices/${id}/verify`, body ?? {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/** Correct what a line says was bought (`PATCH /invoice-lines/{id}`). */
export function updateInvoiceLineMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<
  InvoiceLineRead,
  Error,
  { id: string; body: InvoiceLineUpdate }
> {
  return {
    mutationFn: ({ id, body }) =>
      api.patch<InvoiceLineRead>(`/api/v1/invoice-lines/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/** Add a line to an invoice (`POST /invoices/{id}/lines`). */
export function createInvoiceLineMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<
  InvoiceLineRead,
  Error,
  { invoiceId: string; body: InvoiceLineCreate }
> {
  return {
    mutationFn: ({ invoiceId, body }) =>
      api.post<InvoiceLineRead>(`/api/v1/invoices/${invoiceId}/lines`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/** Delete a line (`DELETE /invoice-lines/{id}`). */
export function deleteInvoiceLineMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<void, Error, { id: string }> {
  return {
    mutationFn: ({ id }) => api.del<void>(`/api/v1/invoice-lines/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/** Queue an invoice's document to be read again (`POST /invoices/{id}/reprocess`). */
export function reprocessInvoiceMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<InvoiceRead, Error, { id: string }> {
  return {
    mutationFn: ({ id }) =>
      api.post<InvoiceRead>(`/api/v1/invoices/${id}/reprocess`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}

/** Verify a line's categorization, optionally correcting it (`POST /invoice-lines/{id}/verify`). */
export function verifyInvoiceLineMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<
  InvoiceLineRead,
  Error,
  { id: string; corrections: LineCorrections }
> {
  return {
    mutationFn: ({ id, corrections }) =>
      api.post<InvoiceLineRead>(
        `/api/v1/invoice-lines/${id}/verify`,
        corrections,
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: entriesKey }),
  }
}
