import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LineStatusBadge } from './line-status'
import type { InvoiceLineRead } from '#/lib/types'

function line(overrides: Partial<InvoiceLineRead> = {}): InvoiceLineRead {
  return {
    id: 'l1',
    invoice_id: 'inv1',
    company_id: 'c1',
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
    verified_fields: [],
    ...overrides,
  }
}

describe('LineStatusBadge', () => {
  it('gives each of the four statuses its own label', () => {
    const labels = (['uncategorized', 'ai_failed', 'ai_categorized', 'verified'] as const).map(
      (status) => {
        const { container, unmount } = render(<LineStatusBadge line={line({ status })} />)
        const text = container.textContent ?? ''
        unmount()
        return text
      },
    )

    expect(new Set(labels).size).toBe(4)
  })

  it('distinguishes a failure from a line nobody has categorized yet', () => {
    // The whole point of the column: both render `—` under Spend category, and
    // only one of them is a problem.
    const { container: failed } = render(<LineStatusBadge line={line({ status: 'ai_failed' })} />)
    const { container: pending } = render(
      <LineStatusBadge line={line({ status: 'uncategorized' })} />,
    )

    expect(failed.textContent).not.toBe(pending.textContent)
  })

  it('presents only the failure as a problem', () => {
    const { container: failed } = render(<LineStatusBadge line={line({ status: 'ai_failed' })} />)
    const { container: pending } = render(
      <LineStatusBadge line={line({ status: 'uncategorized' })} />,
    )
    const { container: verified } = render(
      <LineStatusBadge line={line({ status: 'verified' })} />,
    )

    expect(failed.innerHTML).toContain('destructive')
    // A backlog is not an error, and neither is the goal state. Styling either
    // as one would flag most of the ledger and make the signal worthless.
    expect(pending.innerHTML).not.toContain('destructive')
    expect(verified.innerHTML).not.toContain('destructive')
  })

  it('carries its meaning in text, not colour alone', () => {
    render(<LineStatusBadge line={line({ status: 'ai_failed' })} />)

    expect(screen.getByText(/failed/i)).toBeTruthy()
  })

  it('reads the status from the payload, not from the levels', () => {
    // An `ai_categorized` line whose node was deleted keeps its levels and
    // loses its pointer. It is still AI-categorized.
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
    // `category_stale` is orthogonal to the lifecycle — a line can be verified
    // *and* stale, and a reviewer needs to see both facts.
    render(
      <LineStatusBadge
        line={line({ status: 'verified', level_1: 'Indirect', category_stale: true })}
      />,
    )

    expect(screen.getByText(/Verified/i)).toBeTruthy()
    expect(screen.getByText(/Needs review/i)).toBeTruthy()
  })

  it('does not mark a line that still resolves', () => {
    render(<LineStatusBadge line={line({ status: 'verified', category_stale: false })} />)

    expect(screen.queryByText(/Needs review/i)).toBeNull()
  })
})
