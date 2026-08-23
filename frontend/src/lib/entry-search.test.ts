import { describe, expect, it } from 'vitest'
import {
  applyFilterChange,
  applyVoucherSelection,
  listableEntryTypes,
  validateEntrySearch,
} from './entry-search'

describe('validateEntrySearch', () => {
  it('reads every filter from the URL', () => {
    expect(
      validateEntrySearch({
        company_id: 'c1',
        entry_type: 'purchase_invoice',
        status: 'failed',
        vendor_id: 'v1',
        from: '2026-01-01',
        to: '2026-01-31',
        page: '3',
      }),
    ).toEqual({
      company_id: 'c1',
      entry_type: 'purchase_invoice',
      status: 'failed',
      vendor_id: 'v1',
      from: '2026-01-01',
      to: '2026-01-31',
      page: 3,
    })
  })

  it('leaves unset filters undefined rather than empty strings', () => {
    const parsed = validateEntrySearch({})
    expect(Object.values(parsed).every((value) => value === undefined)).toBe(true)
  })

  it('treats an empty string as unset, so a cleared filter leaves the URL', () => {
    expect(validateEntrySearch({ company_id: '', status: '' })).toMatchObject({
      company_id: undefined,
      status: undefined,
    })
  })

  it('drops page 1 and junk pages, keeping the default URL clean', () => {
    expect(validateEntrySearch({ page: '1' }).page).toBeUndefined()
    expect(validateEntrySearch({ page: 'abc' }).page).toBeUndefined()
    expect(validateEntrySearch({ page: '0' }).page).toBeUndefined()
    expect(validateEntrySearch({ page: '4' }).page).toBe(4)
  })

  it('carries the open voucher and tab', () => {
    expect(validateEntrySearch({ voucher: '4821', tab: 'activity' })).toMatchObject({
      voucher: '4821',
      tab: 'activity',
    })
  })

  it('drops an unknown tab rather than trusting the URL', () => {
    expect(validateEntrySearch({ voucher: '4821', tab: 'evil' }).tab).toBeUndefined()
  })
})

describe('applyFilterChange', () => {
  it('merges the change over the existing filters', () => {
    expect(applyFilterChange({ company_id: 'c1' }, { status: 'failed' })).toMatchObject({
      company_id: 'c1',
      status: 'failed',
    })
  })

  it('resets to page 1, so a narrowed filter cannot strand the user', () => {
    expect(applyFilterChange({ company_id: 'c1', page: 7 }, { status: 'failed' }).page).toBeUndefined()
  })

  it('clears a filter when the change sets it undefined', () => {
    expect(applyFilterChange({ company_id: 'c1' }, { company_id: undefined }).company_id).toBeUndefined()
  })

  it('closes the panel when a filter changes', () => {
    // The open voucher may not survive the new filter; leaving it open would
    // show a panel for a row that is no longer in the list.
    const next = applyFilterChange(
      { voucher: '4821', entry: 'e1', tab: 'details' },
      { company_id: 'c2' },
    )
    expect(next.voucher).toBeUndefined()
    expect(next.entry).toBeUndefined()
    expect(next.tab).toBeUndefined()
  })
})

describe('applyVoucherSelection', () => {
  it('opens the voucher on the tab the caller asked for', () => {
    // A reader who pressed a *line* is asking to see lines. Dropping the tab
    // opened the panel on whichever face it was left on, so the row they
    // activated was not in view — the panel opened over it and showed
    // something else.
    const next = applyVoucherSelection({ tab: 'details' }, { voucher: 'V-1', entry: 'e1', tab: 'lines' })
    expect(next).toMatchObject({ voucher: 'V-1', entry: 'e1', tab: 'lines' })
  })

  it('keeps the tab in view when the caller names none', () => {
    // Opening the next voucher from the voucher row says nothing about which
    // face to show, so the reader stays on the one they were reading.
    expect(applyVoucherSelection({ tab: 'activity' }, { voucher: 'V-2' }).tab).toBe('activity')
  })

  it('keeps the filters the selection says nothing about', () => {
    const next = applyVoucherSelection({ company_id: 'c1', page: 3 }, { voucher: 'V-1' })
    expect(next).toMatchObject({ company_id: 'c1', page: 3 })
  })

  it('clears the tab when the panel closes, so the URL keeps no dead state', () => {
    const next = applyVoucherSelection({ voucher: 'V-1', tab: 'lines' }, {})
    expect(next.voucher).toBeUndefined()
    expect(next.entry).toBeUndefined()
    expect(next.tab).toBeUndefined()
  })
})

describe('listableEntryTypes', () => {
  it('drops the types no listing can return', () => {
    // entries-summary reports over every entry, so it still sees payments —
    // offering one as a filter would only ever produce an empty table.
    expect(listableEntryTypes(['purchase_invoice', 'payment', 'credit_note'])).toEqual([
      'credit_note',
      'purchase_invoice',
    ])
  })

  it('keeps credit notes and journal entries, which move real spend', () => {
    expect(listableEntryTypes(['journal_entry', 'credit_note'])).toEqual([
      'credit_note',
      'journal_entry',
    ])
  })

  it('deduplicates and sorts, since the summary reports one row per currency', () => {
    expect(listableEntryTypes(['purchase_invoice', 'purchase_invoice', 'credit_note'])).toEqual([
      'credit_note',
      'purchase_invoice',
    ])
  })
})
