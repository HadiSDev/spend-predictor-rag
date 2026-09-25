// @vitest-environment node
/** The brand's served files are copies of `brand/`, never re-exports. */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const HERE = dirname(fileURLToPath(import.meta.url))
const repo = (path: string) => join(HERE, '../../..', path)
const pub = (path: string) => join(HERE, '../public', path)

const SERVED_COPIES: Array<[served: string, source: string]> = [
  ['favicon.ico', 'brand/favicon/favicon.ico'],
  ['favicon.svg', 'brand/favicon/favicon.svg'],
  ['apple-touch-icon.png', 'brand/favicon/apple-touch-icon.png'],
  ['favicon-192.png', 'brand/favicon/favicon-192.png'],
  ['favicon-512.png', 'brand/favicon/favicon-512.png'],
  ['og-image-1200x630.png', 'brand/social/og-image-1200x630.png'],
]

describe('served brand assets', () => {
  it.each(SERVED_COPIES)(
    'public/%s is byte-identical to %s',
    (served, source) => {
      expect(readFileSync(pub(served)).equals(readFileSync(repo(source)))).toBe(
        true,
      )
    },
  )

  it('the manifest names the product and uses the pack icons', () => {
    const manifest = JSON.parse(readFileSync(pub('manifest.json'), 'utf8'))
    expect(manifest.name).toBe('Steelyard')
    expect(manifest.short_name).toBe('Steelyard')
    expect(manifest.theme_color).toBe('#0A0A0A')
    const icons = manifest.icons.map((icon: { src: string }) => icon.src)
    expect(icons).toEqual(
      expect.arrayContaining(['favicon-192.png', 'favicon-512.png']),
    )
  })
})
