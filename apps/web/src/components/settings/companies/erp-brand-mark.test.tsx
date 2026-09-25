import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErpBrandMark } from './erp-brand-mark'

describe('ErpBrandMark', () => {
  it('renders the vendored artwork for a slug we have', () => {
    render(<ErpBrandMark slug="billy" label="Billy" />)

    const mark = screen.getByTestId('erp-brand-mark')
    expect(mark.dataset.variant).toBe('artwork')
    expect(mark.querySelector('img')).toBeTruthy()
  })

  it('resolves a slug regardless of case', () => {
    render(<ErpBrandMark slug="BILLY" label="Billy" />)
    expect(screen.getByTestId('erp-brand-mark').dataset.variant).toBe('artwork')
  })

  it('falls back to a lettered tile for a connector we have no artwork for', () => {
    render(<ErpBrandMark slug="not-a-real-erp" label="Visma.net" />)

    const mark = screen.getByTestId('erp-brand-mark')
    expect(mark.dataset.variant).toBe('letter')
    expect(mark.textContent).toBe('V')
  })

  it('falls back when the catalog declares no slug at all', () => {
    render(<ErpBrandMark label="e-conomic" />)

    const mark = screen.getByTestId('erp-brand-mark')
    expect(mark.dataset.variant).toBe('letter')
    expect(mark.textContent).toBe('E')
  })

  it('is hidden from assistive tech, since the label beside it carries the name', () => {
    render(<ErpBrandMark slug="billy" label="Billy" />)
    expect(
      screen.getByTestId('erp-brand-mark').getAttribute('aria-hidden'),
    ).toBe('true')
  })
})
