import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CURRENCIES } from '#/lib/currencies'
import { CountryFlag } from './country-flag'

describe('CountryFlag', () => {
  it('has artwork for every currency on offer', () => {
    // The guard that matters: a mistyped glob or a missing file degrades to the
    // lettered chip, which looks deliberate and would ship unnoticed.
    const missing = CURRENCIES.filter((currency) => {
      const { container, unmount } = render(<CountryFlag country={currency.country} />)
      const img = container.querySelector('img')
      unmount()
      return img === null
    })

    expect(missing.map((c) => `${c.code} (${c.country})`)).toEqual([])
  })

  it('falls back to the country code when there is no flag', () => {
    render(<CountryFlag country="ZZ" />)

    expect(screen.getByText('ZZ')).toBeTruthy()
  })

  it('is decorative — the code and name carry the meaning', () => {
    const { container } = render(<CountryFlag country="DK" />)

    expect(container.firstElementChild?.getAttribute('aria-hidden')).toBe('true')
    expect(container.querySelector('img')?.getAttribute('alt')).toBe('')
  })
})
