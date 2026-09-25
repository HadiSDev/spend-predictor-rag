import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { updateInvoiceMutation, verifyInvoiceLineMutation } from './invoices'
import { entriesKey } from './entries'
import type { ApiClient } from './api-client'

function fakeApi() {
  const calls = {
    patch: vi.fn().mockResolvedValue({ id: 'inv1' }),
    post: vi.fn().mockResolvedValue({ id: 'l1' }),
  }
  return { api: calls as unknown as ApiClient, calls }
}

describe('updateInvoiceMutation', () => {
  it('PATCHes the invoice with only the given changes', async () => {
    const { api, calls } = fakeApi()
    const options = updateInvoiceMutation(api, new QueryClient())

    await options.mutationFn!(
      { id: 'inv1', body: { invoice_number: 'INV-2' } },
      {} as never,
    )

    expect(calls.patch).toHaveBeenCalledWith('/api/v1/invoices/inv1', {
      invoice_number: 'INV-2',
    })
  })

  it('invalidates every entries-family query on success, so the panel, its audit feed and the groups list refresh', async () => {
    const { api } = fakeApi()
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const options = updateInvoiceMutation(api, queryClient)

    await options.onSuccess!(
      { id: 'inv1' } as never,
      { id: 'inv1', body: {} },
      undefined,
      undefined as never,
    )

    expect(invalidate).toHaveBeenCalledWith({ queryKey: entriesKey })
  })
})

describe('verifyInvoiceLineMutation', () => {
  it('POSTs the corrections to the verify endpoint', async () => {
    const { api, calls } = fakeApi()
    const options = verifyInvoiceLineMutation(api, new QueryClient())

    await options.mutationFn!(
      { id: 'l1', corrections: { level_2: 'Furniture' } },
      {} as never,
    )

    expect(calls.post).toHaveBeenCalledWith('/api/v1/invoice-lines/l1/verify', {
      level_2: 'Furniture',
    })
  })

  it('invalidates every entries-family query on success', async () => {
    const { api } = fakeApi()
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const options = verifyInvoiceLineMutation(api, queryClient)

    await options.onSuccess!(
      { id: 'l1' } as never,
      { id: 'l1', corrections: {} },
      undefined,
      undefined as never,
    )

    expect(invalidate).toHaveBeenCalledWith({ queryKey: entriesKey })
  })
})
