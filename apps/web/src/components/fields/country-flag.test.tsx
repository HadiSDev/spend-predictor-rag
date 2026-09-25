import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CountryFlag } from './country-flag'
import { CONVERTIBLE_CURRENCIES, CURRENCIES } from '#/lib/format/currencies'

describe('CountryFlag', () => {
  it('renders artwork for a country the package covers', () => {
    const { container } = render(<CountryFlag country="DK" />)
    const img = container.querySelector('img')

    expect(img).not.toBeNull()
    expect(img?.getAttribute('src')).toBeTruthy()
  })

  it('covers the euro, which is not an ISO 3166-1 country', () => {
    const { container } = render(<CountryFlag country="EU" />)

    expect(container.querySelector('img')).not.toBeNull()
  })

  it('covers every currency an amount can be converted from', () => {
    const missing = CONVERTIBLE_CURRENCIES.filter((currency) => {
      const { container } = render(<CountryFlag country={currency.country} />)
      return container.querySelector('img') === null
    }).map((currency) => `${currency.code} (${currency.country})`)

    expect(missing).toEqual([])
  })

  it('covers all but the handful of currencies that have no country', () => {
    const missing = CURRENCIES.filter((currency) => {
      const { container } = render(<CountryFlag country={currency.country} />)
      return container.querySelector('img') === null
    }).map((currency) => currency.code)

    expect(missing.sort()).toEqual(['ANG', 'XDR', 'XPF', 'XSU'])
  })

  it('falls back to a lettered chip rather than a blank space', () => {
    const { container } = render(<CountryFlag country="ZZ" />)

    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('ZZ')).toBeTruthy()
  })

  it('is decorative, so a screen reader steps over it', () => {
    const { container } = render(<CountryFlag country="DK" />)

    expect(container.firstElementChild?.getAttribute('aria-hidden')).toBe(
      'true',
    )
  })
})
