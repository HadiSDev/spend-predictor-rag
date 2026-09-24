/**
 * The document head's brand metadata: name, icons, theme colour, share card.
 *
 * Kept out of `routes/__root.tsx` so it can be tested without booting Clerk and
 * the devtools. Every file referenced here is served from `public/` as an exact
 * copy of the pack in `brand/` (see `brand.test.ts`).
 */
export const PRODUCT_NAME = 'Steelyard'
export const TAGLINE = 'Know the true price of everything you buy.'
/** The ink: the brand's only colour, and the browser chrome's. */
export const THEME_COLOR = '#0A0A0A'
/**
 * Relative until the app has a production origin; crawlers that require an
 * absolute `og:image` will need one then.
 */
const OG_IMAGE = '/og-image-1200x630.png'

export const BRAND_META = [
  { title: PRODUCT_NAME },
  { name: 'description', content: TAGLINE },
  { name: 'theme-color', content: THEME_COLOR },
  { property: 'og:type', content: 'website' },
  { property: 'og:site_name', content: PRODUCT_NAME },
  { property: 'og:title', content: PRODUCT_NAME },
  { property: 'og:description', content: TAGLINE },
  { property: 'og:image', content: OG_IMAGE },
  { property: 'og:image:width', content: '1200' },
  { property: 'og:image:height', content: '630' },
  { name: 'twitter:card', content: 'summary_large_image' },
  { name: 'twitter:title', content: PRODUCT_NAME },
  { name: 'twitter:description', content: TAGLINE },
  { name: 'twitter:image', content: OG_IMAGE },
]

/** The favicon set, as the pack's README specifies it, plus the manifest. */
export const BRAND_LINKS = [
  { rel: 'icon', href: '/favicon.ico', sizes: '48x48' },
  { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' },
  { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' },
  { rel: 'manifest', href: '/manifest.json' },
]
