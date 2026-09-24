import { describe, expect, it } from 'vitest'
import { fromIsoDate, toIsoDate } from './format'

/**
 * These two were private to `filter-bar.tsx` and untested. They now serve the
 * invoice header's date field as well, where getting them wrong moves a
 * document's date by a day — silently, and only for viewers in some time zones.
 */
describe('toIsoDate / fromIsoDate', () => {
  it('writes a date as the YYYY-MM-DD string the API takes', () => {
    expect(toIsoDate(new Date(2026, 7, 20))).toBe('2026-08-20')
  })

  it('pads single-digit months and days', () => {
    expect(toIsoDate(new Date(2026, 0, 5))).toBe('2026-01-05')
  })

  it('reads an ISO date back as a local date', () => {
    const parsed = fromIsoDate('2026-08-20')
    expect(parsed?.getFullYear()).toBe(2026)
    expect(parsed?.getMonth()).toBe(7)
    expect(parsed?.getDate()).toBe(20)
  })

  it('round-trips without drifting a day', () => {
    // The trap these helpers exist to avoid. `new Date('2026-01-01')` is UTC
    // midnight by specification, and `toISOString().slice(0, 10)` converts back
    // through UTC — so a naive pair reports 2025-12-31 for any viewer behind
    // UTC, and only for them. An invoice date is a calendar date: no time, no
    // zone, and it must survive the trip unchanged.
    for (const iso of ['2026-01-01', '2026-12-31', '2026-06-15', '2024-02-29']) {
      expect(toIsoDate(fromIsoDate(iso))).toBe(iso)
    }
  })

  it('treats absent input as absent, not as the epoch', () => {
    expect(toIsoDate(undefined)).toBeUndefined()
    expect(fromIsoDate(undefined)).toBeUndefined()
    expect(fromIsoDate(null)).toBeUndefined()
    expect(fromIsoDate('')).toBeUndefined()
  })

  it('refuses a string that is not a date rather than returning Invalid Date', () => {
    expect(fromIsoDate('not-a-date')).toBeUndefined()
    expect(fromIsoDate('2026-13-45')).toBeUndefined()
  })
})
