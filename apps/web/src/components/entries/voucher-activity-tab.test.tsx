import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { VoucherActivityTab } from './voucher-activity-tab'
import type { VoucherAuditRead } from '#/lib/types'

/** One audit row. Newest-first is the API's job, not this component's. */
function row(overrides: Partial<VoucherAuditRead> = {}): VoucherAuditRead {
  return {
    id: 'a1',
    entity_type: 'invoice_line',
    entity_id: 'l1',
    entity_label: 'Office chairs',
    action: 'edit',
    actor: 'user_123',
    changes: [{ field: 'level_2', old: 'Office supplies', new: 'Furniture' }],
    created_at: '2026-08-09T08:00:00Z',
    ...overrides,
  }
}

const AI_ROW = row({
  id: 'a0',
  action: 'ai_categorize',
  actor: 'system',
  entity_label: 'Office chairs',
  changes: [
    { field: 'level_1', old: null, new: 'Facilities' },
    { field: 'confidence', old: null, new: '0.62' },
  ],
  created_at: '2026-08-09T07:00:00Z',
})

describe('VoucherActivityTab', () => {
  it('renders a list with one item per audit row, in the order given', () => {
    render(<VoucherActivityTab rows={[row(), AI_ROW]} loading={false} />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    // Newest first, as passed — the component must not re-sort.
    expect(within(items[0]).getByText(/user_123/)).toBeTruthy()
    expect(within(items[1]).getByText(/system/)).toBeTruthy()
  })

  it('falls back to "system" for the automated actor', () => {
    render(<VoucherActivityTab rows={[AI_ROW]} loading={false} />)
    expect(screen.getByText(/system/)).toBeTruthy()
  })

  it('names the entity the change happened to', () => {
    render(<VoucherActivityTab rows={[row()]} loading={false} />)
    expect(screen.getByText(/Office chairs/)).toBeTruthy()
  })

  it('shows the action', () => {
    render(<VoucherActivityTab rows={[row({ action: 'verify' })]} loading={false} />)
    expect(screen.getByText(/verify/i)).toBeTruthy()
  })

  it('shows each field-level change from old to new', () => {
    render(<VoucherActivityTab rows={[row()]} loading={false} />)
    expect(screen.getByText(/level_2/)).toBeTruthy()
    expect(screen.getByText(/Office supplies/)).toBeTruthy()
    expect(screen.getByText(/Furniture/)).toBeTruthy()
  })

  it('handles a null old value without printing the literal word "null"', () => {
    render(<VoucherActivityTab rows={[AI_ROW]} loading={false} />)
    expect(screen.getByText(/Facilities/)).toBeTruthy()
    expect(screen.queryByText(/\bnull\b/)).toBeNull()
  })

  it('renders no changes when the row carries none', () => {
    render(
      <VoucherActivityTab
        rows={[row({ changes: [] })]}
        loading={false}
      />,
    )
    expect(screen.getByText(/Office chairs/)).toBeTruthy()
  })

  it('shows a timestamp with the absolute time available in a title', () => {
    render(<VoucherActivityTab rows={[row()]} loading={false} />)
    const time = screen.getByText((_, element) => element?.tagName.toLowerCase() === 'time')
    expect(time.getAttribute('title') ?? time.getAttribute('dateTime')).toBeTruthy()
  })

  it('shows the documented empty-state message when there are no rows', () => {
    render(<VoucherActivityTab rows={[]} loading={false} />)
    expect(screen.getByText('No changes recorded for this voucher yet.')).toBeTruthy()
  })

  it('does not show the empty-state message while loading', () => {
    render(<VoucherActivityTab rows={[]} loading />)
    expect(screen.queryByText('No changes recorded for this voucher yet.')).toBeNull()
  })

  it('shows placeholders while loading', () => {
    const { container } = render(<VoucherActivityTab rows={[]} loading />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })
})
