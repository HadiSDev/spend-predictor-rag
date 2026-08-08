import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { accountsKey, accountsQueryOptions, refreshAccountsMutation, updateAccountMutation } from './accounts'
import type { ApiClient } from './api-client'

function fakeApi() {
  const calls = { get: vi.fn().mockResolvedValue([]), patch: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({ seen: 2, added: 0 }) }
  return { api: calls as unknown as ApiClient, calls }
}

describe('accountsQueryOptions', () => {
  it('reads the chart through the integration', async () => {
    const { api, calls } = fakeApi()
    await accountsQueryOptions(api, 'i1').queryFn!({} as never)
    expect(calls.get.mock.calls[0][0]).toBe('/api/v1/erp-integrations/i1/accounts')
  })

  it('stays disabled without an integration, so a company with none fires nothing', () => {
    const { api } = fakeApi()
    expect(accountsQueryOptions(api, null).enabled).toBe(false)
    expect(accountsQueryOptions(api, 'i1').enabled).toBe(true)
  })
})

describe('updateAccountMutation', () => {
  it('patches only the account it was given', async () => {
    const { api, calls } = fakeApi()
    const options = updateAccountMutation(api, new QueryClient(), 'i1')

    await options.mutationFn!({ id: 'a1', body: { with_vat: false } }, {} as never)

    expect(calls.patch.mock.calls[0][0]).toBe('/api/v1/erp-accounts/a1')
    expect(calls.patch.mock.calls[0][1]).toEqual({ with_vat: false })
  })

  it("invalidates that integration's chart on success", async () => {
    const { api } = fakeApi()
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const options = updateAccountMutation(api, queryClient, 'i1')

    await options.onSuccess!({} as never, { id: 'a1', body: {} }, undefined as never, undefined as never)

    expect(invalidate).toHaveBeenCalledWith({ queryKey: accountsKey('i1') })
  })
})

describe('refreshAccountsMutation', () => {
  it('posts to the integration and returns what the refresh found', async () => {
    const { api, calls } = fakeApi()
    const options = refreshAccountsMutation(api, new QueryClient(), 'i1')

    const result = await options.mutationFn!(undefined as never, {} as never)

    expect(calls.post.mock.calls[0][0]).toBe('/api/v1/erp-integrations/i1/refresh-accounts')
    expect(result).toEqual({ seen: 2, added: 0 })
  })
})
