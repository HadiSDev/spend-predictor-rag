import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Logo, MIN_LOCKUP_WIDTH, MIN_SYMBOL_WIDTH, WORDMARK_PATH } from './logo'

// Joined by hand: Vite rewrites `new URL(<relative>, import.meta.url)` into an
// asset import, and its fs guard refuses files outside apps/web.
const REPO = join(dirname(fileURLToPath(import.meta.url)), '../../../../..')
const brand = (path: string) => readFileSync(join(REPO, 'brand', path), 'utf8')

describe('Logo', () => {
  it('is an image named Steelyard, with no text node spelling the name', () => {
    const { container } = render(<Logo width={140} />)
    const logo = screen.getByRole('img', { name: 'Steelyard' })
    expect(logo.tagName.toLowerCase()).toBe('svg')
    // Rendered from outlines, never retyped.
    expect(container.textContent).toBe('')
  })

  it("draws the wordmark from the pack's outlines, verbatim", () => {
    const pack = brand('svg/steelyard-lockup-black.svg')
    expect(pack).toContain(`d="${WORDMARK_PATH}"`)
  })

  it('paints only in currentColor, so the theme decides black or white', () => {
    const { container } = render(<Logo width={140} />)
    const svg = container.querySelector('svg')!
    expect(svg.getAttribute('fill')).toBe('currentColor')
    for (const el of container.querySelectorAll('[fill], [stroke], [style]')) {
      if (el === svg) continue
      throw new Error(
        `a descendant sets its own paint: ${el.outerHTML.slice(0, 80)}`,
      )
    }
  })

  it('never renders below the pack minimums', () => {
    const { rerender, container } = render(<Logo width={10} />)
    expect(container.querySelector('svg')!.getAttribute('width')).toBe(
      String(MIN_LOCKUP_WIDTH),
    )
    rerender(<Logo variant="symbol" width={4} />)
    expect(container.querySelector('svg')!.getAttribute('width')).toBe(
      String(MIN_SYMBOL_WIDTH),
    )
  })

  it('uses the favicon geometry below 32 px, and the standard one from 32 px', () => {
    const { rerender, container } = render(<Logo variant="symbol" width={24} />)
    const svg = () => container.querySelector('svg')!
    expect(svg().dataset.variant).toBe('symbol-small')
    // The favicon's thicker arm: 8 units against the standard 6.
    expect(svg().querySelector('rect')!.getAttribute('height')).toBe('8')
    rerender(<Logo variant="symbol" width={32} />)
    expect(svg().dataset.variant).toBe('symbol')
    expect(svg().querySelector('rect')!.getAttribute('height')).toBe('6')
  })

  it('keeps the geometry of the pack symbol and favicon', () => {
    expect(brand('svg/steelyard-symbol-black.svg')).toContain(
      '<circle cx="18" cy="32" r="12"/><rect x="18" y="29" width="36" height="6"/><circle cx="54" cy="32" r="6"/>',
    )
    expect(brand('favicon/favicon.svg')).toContain(
      '<circle cx="21" cy="32" r="11"/><rect x="21" y="28" width="26" height="8"/><circle cx="47" cy="32" r="7"/>',
    )
  })
})
