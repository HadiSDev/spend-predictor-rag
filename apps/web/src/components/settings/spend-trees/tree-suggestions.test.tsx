import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { TreeSuggestions } from './tree-suggestions'
import type { SpendCategorySuggestionRead } from '#/lib/api/types'

function suggestion(
  overrides: Partial<SpendCategorySuggestionRead> = {},
): SpendCategorySuggestionRead {
  return {
    id: 's1',
    spend_tree_id: 't1',
    company_id: 'c1',
    parent_id: 'n-travel',
    parent_path: 'Indirect > Travel & Entertainment',
    name: 'Ground Transport',
    description: 'Rail, bus and taxi.',
    rationale: 'Rail travel has no home in this tree.',
    state: 'pending',
    created_category_id: null,
    acceptable: true,
    evidence: [
      {
        id: 'l1',
        item_name: 'Togbillet',
        description: null,
        amount: '58.00',
        currency: 'DKK',
        vendor_name: 'DSB',
        invoice_id: 'inv1',
        level_1: 'Indirect',
        level_2: 'Travel & Entertainment',
        level_3: 'Airfare',
        confidence: '0.200',
      },
    ],
    evidence_count: 1,
    created_at: null,
    ...overrides,
  }
}

const noop = () => Promise.resolve()

function setup(
  props: Partial<React.ComponentProps<typeof TreeSuggestions>> = {},
) {
  return render(
    <TreeSuggestions
      suggestions={[suggestion()]}
      canManage
      onAccept={noop}
      onDismiss={noop}
      onReopen={noop}
      {...props}
    />,
  )
}

describe('TreeSuggestions', () => {
  it('names the proposal and where it would go', () => {
    setup()

    expect(screen.getByText('Ground Transport')).toBeTruthy()
    expect(
      screen.getByText(/under Indirect > Travel & Entertainment/),
    ).toBeTruthy()
  })

  it('gives the reason the tree needs it', () => {
    setup()

    expect(screen.getByText(/Rail travel has no home/)).toBeTruthy()
  })

  it('renders nothing when there is nothing pending', () => {
    const { container } = setup({ suggestions: [] })

    expect(container.textContent).toBe('')
  })

  it('ignores suggestions that are already settled', () => {
    const { container } = setup({
      suggestions: [
        suggestion({ state: 'dismissed' }),
        suggestion({ id: 's2', state: 'accepted' }),
      ],
    })

    expect(container.textContent).toBe('')
  })

  describe('evidence', () => {
    it('is reachable, because a proposal nobody can check cannot be accepted', async () => {
      setup()

      fireEvent.click(screen.getByRole('button', { name: /show the lines/i }))

      expect(screen.getByText('Togbillet')).toBeTruthy()
      expect(screen.getByText('DSB')).toBeTruthy()
    })

    it('says where each line actually landed, which is half the argument', async () => {
      setup()

      fireEvent.click(screen.getByRole('button', { name: /show the lines/i }))

      expect(screen.getByText(/filed under Airfare/)).toBeTruthy()
    })

    it('opens the line it names', async () => {
      const onOpenLine = vi.fn()
      setup({ onOpenLine })

      fireEvent.click(screen.getByRole('button', { name: /show the lines/i }))
      fireEvent.click(screen.getByRole('button', { name: 'Togbillet' }))

      expect(onOpenLine).toHaveBeenCalledWith({ id: 'l1', invoiceId: 'inv1' })
    })
  })

  describe('acting on one', () => {
    it('accepts', async () => {
      const onAccept = vi.fn(() => Promise.resolve())
      setup({ onAccept })

      fireEvent.click(screen.getByRole('button', { name: /add to tree/i }))

      expect(onAccept).toHaveBeenCalledWith('s1')
    })

    it('will not accept one whose parent is gone', () => {
      setup({
        suggestions: [suggestion({ acceptable: false, parent_path: null })],
      })

      expect(
        screen.getByRole('button', { name: /add to tree/i }),
      ).toHaveProperty('disabled', true)
      expect(screen.getByText(/parent no longer exists/i)).toBeTruthy()
    })

    it('offers a real undo after a dismissal', async () => {
      const onReopen = vi.fn(() => Promise.resolve())
      setup({ onReopen })

      fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /undo/i })).toBeTruthy(),
      )
      fireEvent.click(screen.getByRole('button', { name: /undo/i }))

      expect(onReopen).toHaveBeenCalledWith('s1')
    })

    it('reports a failure instead of pretending it worked', async () => {
      setup({
        onAccept: () => Promise.reject(new Error('Category already exists.')),
      })

      fireEvent.click(screen.getByRole('button', { name: /add to tree/i }))

      await waitFor(() =>
        expect(screen.getByRole('alert').textContent).toContain(
          'Category already exists.',
        ),
      )
    })
  })

  describe('a read-only role', () => {
    it('sees the proposal and its evidence', async () => {
      setup({ canManage: false })

      expect(screen.getByText('Ground Transport')).toBeTruthy()
      fireEvent.click(screen.getByRole('button', { name: /show the lines/i }))
      expect(screen.getByText('Togbillet')).toBeTruthy()
    })

    it('is shown no controls at all, not disabled ones', () => {
      setup({ canManage: false })

      expect(screen.queryByRole('button', { name: /add to tree/i })).toBeNull()
      expect(screen.queryByRole('button', { name: /dismiss/i })).toBeNull()
    })
  })
})
