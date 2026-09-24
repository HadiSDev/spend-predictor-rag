import { describe, expect, it } from 'vitest'
import { COUNTRIES, countryLabel, findCountry, foldForSearch } from './countries'

describe('COUNTRIES', () => {
  it('holds every ISO 3166-1 officially assigned code, once', () => {
    expect(COUNTRIES).toHaveLength(249)
    expect(new Set(COUNTRIES.map((c) => c.code)).size).toBe(249)
  })

  it('carries uppercase two-letter codes and non-empty names', () => {
    const malformed = COUNTRIES.filter((c) => !/^[A-Z]{2}$/.test(c.code) || c.name.trim() === '')
    expect(malformed).toEqual([])
  })

  it('excludes codes that name no country', () => {
    // `EU` belongs to the currency list (the euro's issuer) and `UK`/`XK` are
    // reserved rather than assigned — a company cannot be registered in any.
    for (const code of ['EU', 'UK', 'XK', 'AN', 'SU', 'ZZ']) {
      expect(findCountry(code)).toBeUndefined()
    }
  })
})

describe('findCountry', () => {
  it('resolves a canonical code', () => {
    expect(findCountry('DK')?.name).toBe('Denmark')
  })

  it('resolves what the free-text field it replaced allowed', () => {
    expect(findCountry('dk')?.code).toBe('DK')
    expect(findCountry(' Dk ')?.code).toBe('DK')
  })

  it('resolves nothing for an unassigned code or no value', () => {
    expect(findCountry('ZZ')).toBeUndefined()
    expect(findCountry('')).toBeUndefined()
    expect(findCountry(null)).toBeUndefined()
  })
})

describe('countryLabel', () => {
  it('leads with the code, which is what gets stored', () => {
    expect(countryLabel({ code: 'DK', name: 'Denmark' })).toBe('DK — Denmark')
  })
})

describe('foldForSearch', () => {
  it('makes accented names reachable without the accent', () => {
    expect(foldForSearch('Åland Islands')).toContain('aland')
    expect(foldForSearch('Côte d’Ivoire')).toContain('cote')
    expect(foldForSearch('Curaçao')).toBe('curacao')
  })
})
