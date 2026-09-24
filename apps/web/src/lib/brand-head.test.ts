import { describe, expect, it } from 'vitest'

import { BRAND_LINKS, BRAND_META } from './brand-head'

describe('brand head', () => {
  it('names the product and sets the ink as theme colour', () => {
    expect(BRAND_META).toContainEqual({ title: 'Steelyard' })
    expect(BRAND_META).toContainEqual({
      name: 'theme-color',
      content: '#0A0A0A',
    })
  })

  it('declares the share card from the pack', () => {
    expect(BRAND_META).toContainEqual({
      property: 'og:title',
      content: 'Steelyard',
    })
    expect(BRAND_META).toContainEqual({
      property: 'og:image',
      content: '/og-image-1200x630.png',
    })
    expect(BRAND_META).toContainEqual({
      property: 'og:description',
      content: 'Know the true price of everything you buy.',
    })
    expect(BRAND_META).toContainEqual({
      name: 'twitter:card',
      content: 'summary_large_image',
    })
  })

  it('links the favicon set the pack README specifies', () => {
    expect(BRAND_LINKS).toEqual(
      expect.arrayContaining([
        { rel: 'icon', href: '/favicon.ico', sizes: '48x48' },
        { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' },
        { rel: 'manifest', href: '/manifest.json' },
      ]),
    )
  })
})
