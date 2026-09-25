import { describe, expect, it, vi } from 'vitest'
import {
  entriesKey,
  entryQueryOptions,
  invoiceDocumentQueryOptions,
  voucherAuditQueryOptions,
  voucherDetailQueryOptions,
  voucherGroupsQueryOptions,
} from './entries'
import { vendorsQueryOptions } from './vendors'
import type { ApiClient } from './api-client'

function fakeApi() {
  const get = vi
    .fn()
    .mockResolvedValue({ items: [], page: 1, page_size: 25, total: 0 })
  const getBlob = vi.fn().mockResolvedValue(new Blob())
  return { api: { get, getBlob } as unknown as ApiClient, get, getBlob }
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

describe('voucherDetailQueryOptions', () => {
  it('addresses a real voucher by id', () => {
    const { api } = fakeApi()
    expect(
      voucherDetailQueryOptions(api, { voucher: '4821' }).queryKey,
    ).toContain('4821')
  })

  it('is disabled when nothing is selected', () => {
    const { api } = fakeApi()
    expect(voucherDetailQueryOptions(api, {}).enabled).toBe(false)
  })

  it('fetches by voucher id when one is given', async () => {
    const { api, get } = fakeApi()

    await voucherDetailQueryOptions(api, { voucher: '4821' }).queryFn!(
      {} as never,
    )

    expect(get.mock.calls[0][0]).toBe('/api/v1/erp-entries/vouchers/4821')
  })

  it('falls back to the entry id when there is no voucher id', async () => {
    const { api, get } = fakeApi()

    await voucherDetailQueryOptions(api, { entry: 'e1' }).queryFn!({} as never)

    expect(get.mock.calls[0][0]).toBe(
      '/api/v1/erp-entries/vouchers/by-entry/e1',
    )
    expect(voucherDetailQueryOptions(api, { entry: 'e1' }).enabled).toBe(true)
  })

  it('prefers the voucher id over the entry id when both are given', async () => {
    const { api, get } = fakeApi()

    await voucherDetailQueryOptions(api, { voucher: '4821', entry: 'e1' })
      .queryFn!({} as never)

    expect(get.mock.calls[0][0]).toBe('/api/v1/erp-entries/vouchers/4821')
  })

  it('asks for base mode, same as the voucher groups the drawer is opened from', async () => {
    const { api, get } = fakeApi()

    await voucherDetailQueryOptions(api, { voucher: '4821' }).queryFn!(
      {} as never,
    )

    expect(get.mock.calls[0][1]).toEqual({ currency_mode: 'base' })
  })
})

describe('voucherAuditQueryOptions', () => {
  it('fetches the audit feed for a voucher id', async () => {
    const { api, get } = fakeApi()

    await voucherAuditQueryOptions(api, { voucher: '4821' }).queryFn!(
      {} as never,
    )

    expect(get.mock.calls[0][0]).toBe('/api/v1/erp-entries/vouchers/4821/audit')
  })

  it('fetches the audit feed by entry id when there is no voucher id', async () => {
    const { api, get } = fakeApi()

    await voucherAuditQueryOptions(api, { entry: 'e1' }).queryFn!({} as never)

    expect(get.mock.calls[0][0]).toBe(
      '/api/v1/erp-entries/vouchers/by-entry/e1/audit',
    )
  })

  it('is disabled when nothing is selected', () => {
    const { api } = fakeApi()
    expect(voucherAuditQueryOptions(api, {}).enabled).toBe(false)
  })
})

describe('invoiceDocumentQueryOptions', () => {
  it('fetches the invoice document as a blob', async () => {
    const { api, getBlob } = fakeApi()

    await invoiceDocumentQueryOptions(api, 'inv1').queryFn!({} as never)

    expect(getBlob.mock.calls[0][0]).toBe('/api/v1/invoices/inv1/document')
  })

  it('is disabled with no invoice id, never refetches, and never retries', () => {
    const { api } = fakeApi()
    expect(invoiceDocumentQueryOptions(api, null).enabled).toBe(false)
    expect(invoiceDocumentQueryOptions(api, 'inv1').enabled).toBe(true)
    expect(invoiceDocumentQueryOptions(api, 'inv1').staleTime).toBe(Infinity)
    expect(invoiceDocumentQueryOptions(api, 'inv1').retry).toBe(false)
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
