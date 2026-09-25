import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LineStatusBadge } from './line-status'
import type { InvoiceLineRead } from '#/lib/api/types'

function line(overrides: Partial<InvoiceLineRead> = {}): InvoiceLineRead {
  return {
    id: 'l1',
    invoice_id: 'inv1',
    company_id: 'c1',
    item_name: null,
    description: 'Togbillet',
    quantity: null,
    unit: null,
    unit_price: null,
    amount: '11.20',
    native_account_code: '1620',
    base_currency: 'DKK',
    base_amount: '11.20',
    fx_rate: '1',
    fx_rate_date: '2026-04-12',
    origin: 'erp',
    sequence: 0,
    currency: 'DKK',
    status: 'ai_failed',
    level_1: null,
    level_2: null,
    level_3: null,
    level_4: null,
    account_code: null,
    account_name: null,
    confidence: null,
    rationale: null,
    spend_category_id: null,
    category_stale: false,
    needs_review: false,
    verified_fields: [],
    ...overrides,
  }
}

describe('LineStatusBadge', () => {
  it('gives each of the four statuses its own label', () => {
    const labels = (
      ['uncategorized', 'ai_failed', 'ai_categorized', 'verified'] as const
    ).map((status) => {
      const { container, unmount } = render(
        <LineStatusBadge line={line({ status })} />,
      )
      const text = container.textContent ?? ''
      unmount()
      return text
    })

    expect(new Set(labels).size).toBe(4)
  })

  it('distinguishes a failure from a line nobody has categorized yet', () => {
    const { container: failed } = render(
      <LineStatusBadge line={line({ status: 'ai_failed' })} />,
    )
    const { container: pending } = render(
      <LineStatusBadge line={line({ status: 'uncategorized' })} />,
    )

    expect(failed.textContent).not.toBe(pending.textContent)
  })

  it('presents only the failure as a problem', () => {
    const { container: failed } = render(
      <LineStatusBadge line={line({ status: 'ai_failed' })} />,
    )
    const { container: pending } = render(
      <LineStatusBadge line={line({ status: 'uncategorized' })} />,
    )
    const { container: verified } = render(
      <LineStatusBadge line={line({ status: 'verified' })} />,
    )

    expect(failed.innerHTML).toContain('destructive')
    expect(pending.innerHTML).not.toContain('destructive')
    expect(verified.innerHTML).not.toContain('destructive')
  })

  it('carries its meaning in text, not colour alone', () => {
    render(<LineStatusBadge line={line({ status: 'ai_failed' })} />)

    expect(screen.getByText(/failed/i)).toBeTruthy()
  })

  it('reads the status from the payload, not from the levels', () => {
    render(
      <LineStatusBadge
        line={line({
          status: 'ai_categorized',
          level_1: 'Indirect',
          level_2: 'Technology',
          spend_category_id: null,
          category_stale: true,
        })}
      />,
    )

    expect(screen.getByText(/AI categorized/i)).toBeTruthy()
  })

  it('shows a stale line as both its status and needing review', () => {
    render(
      <LineStatusBadge
        line={line({
          status: 'verified',
          level_1: 'Indirect',
          category_stale: true,
        })}
      />,
    )

    expect(screen.getByText(/Verified/i)).toBeTruthy()
    expect(screen.getByText(/Unresolved category/i)).toBeTruthy()
  })

  it('does not mark a line that still resolves', () => {
    render(
      <LineStatusBadge
        line={line({ status: 'verified', category_stale: false })}
      />,
    )

    expect(screen.queryByText(/Unresolved category/i)).toBeNull()
  })
})

describe('low confidence', () => {
  it('marks a line the AI was unsure about', () => {
    render(
      <LineStatusBadge
        line={line({ status: 'ai_categorized', needs_review: true })}
      />,
    )

    expect(screen.getByText('Low confidence')).toBeTruthy()
  })

  it('says nothing about a confident line', () => {
    render(
      <LineStatusBadge
        line={line({ status: 'ai_categorized', needs_review: false })}
      />,
    )

    expect(screen.queryByText('Low confidence')).toBeNull()
  })

  it('names its own cause rather than the work it implies', () => {
    render(
      <LineStatusBadge
        line={line({
          status: 'ai_categorized',
          needs_review: true,
          category_stale: true,
        })}
      />,
    )

    expect(screen.getByText('Low confidence')).toBeTruthy()
    expect(screen.getByText('Unresolved category')).toBeTruthy()
  })
})
