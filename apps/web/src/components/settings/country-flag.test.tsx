import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CountryFlag } from './country-flag'

/**
 * The artwork moved from 31 hand-vendored files to `country-flag-icons`. Six of
 * the vendored ones were broken — the vendoring pass stripped ids, and the
 * flags that place stars and emblems through `<use xlink:href="#…">` were left
 * pointing at nothing, so they painted as bare fields of colour. Nothing caught
 * that, because nothing asserted a flag had actually rendered.
 */
describe('CountryFlag', () => {
  it('renders artwork for a country the package covers', () => {
    const { container } = render(<CountryFlag country="DK" />)
    const img = container.querySelector('img')

    expect(img).not.toBeNull()
    expect(img?.getAttribute('src')).toBeTruthy()
  })

  it('covers the euro, which is not an ISO 3166-1 country', () => {
    // The one that showed as a plain blue disc. It has no country code of its
    // own, so a package covering only ISO 3166-1 would not carry it.
    const { container } = render(<CountryFlag country="EU" />)

    expect(container.querySelector('img')).not.toBeNull()
  })

  it('covers every currency an amount can be converted from', async () => {
    // The convertible set is what nearly every customer picks, and a missing
    // flag there is a gap someone will see. The full ISO list is a different
    // promise — see below.
    const { CONVERTIBLE_CURRENCIES } = await import('#/lib/currencies')
    const missing = CONVERTIBLE_CURRENCIES.filter((currency) => {
      const { container } = render(<CountryFlag country={currency.country} />)
      return container.querySelector('img') === null
    }).map((currency) => `${currency.code} (${currency.country})`)

    expect(missing).toEqual([])
  })

  it('covers all but the handful of currencies that have no country', async () => {
    // `XDR`, `XPF` and `XSU` are supranational and issued by no country;
    // `ANG`'s `AN` was withdrawn from ISO 3166-1. There is no flag to show for
    // any of them, which is what the lettered chip is for — so this asserts the
    // *size* of the gap rather than pretending there is none.
    const { CURRENCIES } = await import('#/lib/currencies')
    const missing = CURRENCIES.filter((currency) => {
      const { container } = render(<CountryFlag country={currency.country} />)
      return container.querySelector('img') === null
    }).map((currency) => currency.code)

    expect(missing.sort()).toEqual(['ANG', 'XDR', 'XPF', 'XSU'])
  })

  it('falls back to a lettered chip rather than a blank space', () => {
    // Deliberate, not an edge case: the country picker lists every ISO 3166-1
    // code, and a blank coin would read as a failed image.
    const { container } = render(<CountryFlag country="ZZ" />)

    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('ZZ')).toBeTruthy()
  })

  it('is decorative, so a screen reader steps over it', () => {
    // The code and name beside it carry the meaning; repeating the country
    // would only put noise between them.
    const { container } = render(<CountryFlag country="DK" />)

    expect(container.firstElementChild?.getAttribute('aria-hidden')).toBe('true')
  })
})
