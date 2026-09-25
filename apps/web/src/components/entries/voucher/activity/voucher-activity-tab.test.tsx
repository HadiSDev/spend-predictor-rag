import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { VoucherActivityTab } from './voucher-activity-tab'
import type { VoucherAuditRead } from '#/lib/api/types'

function row(overrides: Partial<VoucherAuditRead> = {}): VoucherAuditRead {
  return {
    id: 'a1',
    entity_type: 'invoice_line',
    entity_id: 'l1',
    entity_label: 'Office chairs',
    action: 'edit',
    actor: 'a15bb8fe-da2b-4626-a852-119ec6e29bfd',
    actor_name: 'Hadi Salameh',
    changes: [{ field: 'level_2', old: 'Office supplies', new: 'Furniture' }],
    created_at: '2026-08-09T08:00:00Z',
    ...overrides,
  }
}

const LONG_REASONING =
  'The invoice line is from supplier DSB for 58.00 DKK. DSB is a major Danish utility provider, so despite the generic item description the spend maps to utilities. Electricity and heating for the office are booked to the same account every month, which supports the match.'

const AI_ROW = row({
  id: 'a0',
  action: 'ai_categorize',
  actor: 'system',
  actor_name: null,
  changes: [
    { field: 'level_1', old: null, new: 'Facilities' },
    { field: 'confidence', old: null, new: '0.62' },
    { field: 'rationale', old: null, new: LONG_REASONING },
  ],
  created_at: '2026-08-09T07:00:00Z',
})

describe('VoucherActivityTab', () => {
  it('renders one list item per audit row, in the order given', () => {
    render(<VoucherActivityTab rows={[row(), AI_ROW]} loading={false} />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(within(items[0]).getByText('Hadi Salameh')).toBeTruthy()
    expect(within(items[1]).getByText('Steelyard AI')).toBeTruthy()
  })

  it('names the person instead of printing their id', () => {
    render(<VoucherActivityTab rows={[row()]} loading={false} />)
    expect(screen.queryByText(/a15bb8fe/)).toBeNull()
  })

  it('reads each event as a sentence about the entity', () => {
    render(<VoucherActivityTab rows={[row()]} loading={false} />)
    expect(screen.getByRole('listitem').textContent).toContain(
      'Hadi Salameh corrected Office chairs',
    )
  })

  it('shows the category it moved from and to, not the raw field name', () => {
    render(<VoucherActivityTab rows={[row()]} loading={false} />)
    expect(screen.getByText('Office supplies')).toBeTruthy()
    expect(screen.getByText('Furniture')).toBeTruthy()
    expect(screen.queryByText(/level_2/)).toBeNull()
  })

  it('shows confidence as a percentage', () => {
    render(<VoucherActivityTab rows={[AI_ROW]} loading={false} />)
    expect(screen.getByText('62% confidence')).toBeTruthy()
  })

  it('never prints the literal word "null"', () => {
    render(<VoucherActivityTab rows={[AI_ROW]} loading={false} />)
    expect(screen.queryByText(/\bnull\b/)).toBeNull()
  })

  it('folds long reasoning behind a toggle', () => {
    render(<VoucherActivityTab rows={[AI_ROW]} loading={false} />)
    const toggle = screen.getByRole('button', { name: 'Show more' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(toggle)
    expect(
      screen
        .getByRole('button', { name: 'Show less' })
        .getAttribute('aria-expanded'),
    ).toBe('true')
  })

  it('groups events under a heading for their day', () => {
    render(
      <VoucherActivityTab
        rows={[row(), row({ id: 'a9', created_at: '2026-07-01T08:00:00Z' })]}
        loading={false}
      />,
    )
    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(2)
  })

  it('renders an event with no changes', () => {
    render(<VoucherActivityTab rows={[row({ changes: [] })]} loading={false} />)
    expect(screen.getByText('Office chairs')).toBeTruthy()
  })

  it('shows a timestamp with the absolute time in a title', () => {
    render(<VoucherActivityTab rows={[row()]} loading={false} />)
    const time = screen.getByText(
      (_, element) => element?.tagName.toLowerCase() === 'time',
    )
    expect(time.getAttribute('title')).toBeTruthy()
    expect(time.getAttribute('dateTime')).toBe('2026-08-09T08:00:00Z')
  })

  it('shows the documented empty-state message when there are no rows', () => {
    render(<VoucherActivityTab rows={[]} loading={false} />)
    expect(
      screen.getByText('No changes recorded for this voucher yet.'),
    ).toBeTruthy()
  })

  it('does not show the empty-state message while loading', () => {
    render(<VoucherActivityTab rows={[]} loading />)
    expect(
      screen.queryByText('No changes recorded for this voucher yet.'),
    ).toBeNull()
  })

  it('shows placeholders while loading', () => {
    const { container } = render(<VoucherActivityTab rows={[]} loading />)
    expect(
      container.querySelectorAll('[class*="animate-pulse"]').length,
    ).toBeGreaterThan(0)
  })
})
