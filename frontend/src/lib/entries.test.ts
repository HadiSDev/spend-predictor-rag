import { describe, expect, it, vi } from 'vitest'
import { entriesKey, entryQueryOptions, voucherGroupsQueryOptions } from './entries'
import { vendorsQueryOptions } from './vendors'
import type { ApiClient } from './api-client'

function fakeApi() {
  const get = vi.fn().mockResolvedValue({ items: [], page: 1, page_size: 25, total: 0 })
  return { api: { get } as unknown as ApiClient, get }
}

describe('voucherGroupsQueryOptions', () => {
  it('hits the voucher endpoint and passes the filters through', async () => {
    const { api, get } = fakeApi()
    const options = voucherGroupsQueryOptions(api, {
      company_id: 'c1',
      from: '2026-01-01',
      to: '2026-01-31',
      vendor_id: 'v1',
      status: 'failed',
      page: 2,
    })

    await options.queryFn!({} as never)

    const [path, params] = get.mock.calls[0]
    expect(path).toBe('/api/v1/erp-entries/vouchers')
    expect(params).toEqual({
      // Base mode is always asked for, so the table's currency labels cannot be
      // changed out from under it by a server-side default.
      currency_mode: 'base',
      company_id: 'c1',
      from: '2026-01-01',
      to: '2026-01-31',
      vendor_id: 'v1',
      status: 'failed',
      page: 2,
    })
  })

  it('sends only the currency mode when no filters are set', async () => {
    const { api, get } = fakeApi()

    await voucherGroupsQueryOptions(api).queryFn!({} as never)

    expect(get.mock.calls[0][1]).toEqual({ currency_mode: 'base' })
  })

  it('keys the cache off the filters, so each combination caches separately', () => {
    const { api } = fakeApi()
    const a = voucherGroupsQueryOptions(api, { company_id: 'c1' }).queryKey
    const b = voucherGroupsQueryOptions(api, { company_id: 'c2' }).queryKey

    expect(a).not.toEqual(b)
    expect(a.slice(0, 2)).toEqual([...entriesKey, 'vouchers'])
  })
})

describe('entryQueryOptions', () => {
  it('fetches one entry by id', async () => {
    const { api, get } = fakeApi()

    await entryQueryOptions(api, 'e1').queryFn!({} as never)

    expect(get.mock.calls[0][0]).toBe('/api/v1/erp-entries/e1')
  })

  it('stays disabled with no id, so no request fires for a closed drawer', () => {
    const { api } = fakeApi()
    expect(entryQueryOptions(api, null).enabled).toBe(false)
    expect(entryQueryOptions(api, 'e1').enabled).toBe(true)
  })
})

describe('vendorsQueryOptions', () => {
  it('passes the search term and drops an empty one', async () => {
    const { api, get } = fakeApi()

    await vendorsQueryOptions(api, { q: 'acme' }).queryFn!({} as never)
    expect(get.mock.calls[0][1]).toEqual({ q: 'acme' })

    await vendorsQueryOptions(api, { q: '' }).queryFn!({} as never)
    expect(get.mock.calls[1][1]).toEqual({ q: undefined })
  })
})
