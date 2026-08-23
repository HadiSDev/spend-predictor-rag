import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LineEditor } from './line-editor'
import type { InvoiceLineRead } from '#/lib/types'

/** A three-level tree matching the line fixtures above. */
const TREE_NODES = [
  { id: 'n1', spend_tree_id: 'tree1', parent_id: null, depth: 1, name: 'Facilities',
    code: null, sort_order: 0, description: null,
    level_1: 'Facilities', level_2: null, level_3: null, level_4: null },
  { id: 'n2', spend_tree_id: 'tree1', parent_id: 'n1', depth: 2, name: 'Furniture',
    code: null, sort_order: 0, description: null,
    level_1: 'Facilities', level_2: 'Furniture', level_3: null, level_4: null },
  { id: 'cat-chairs', spend_tree_id: 'tree1', parent_id: 'n2', depth: 3, name: 'Office chairs',
    code: '6100', sort_order: 0, description: null,
    level_1: 'Facilities', level_2: 'Furniture', level_3: 'Office chairs', level_4: null },
]


/** One categorized line — the shape every voucher's AI result takes. */
function line(overrides: Partial<InvoiceLineRead> = {}): InvoiceLineRead {
  return {
    id: 'l2',
    invoice_id: 'inv1',
    company_id: 'c1',
    item_name: null,
    description: 'Office chairs',
    quantity: '2',
    unit: null,
    unit_price: '450.00',
    amount: '900.00',
    native_account_code: null,
    base_currency: 'DKK',
    base_amount: '900.00',
    fx_rate: '1',
    fx_rate_date: '2026-04-12',
    origin: 'document_ai',
    sequence: 0,
    currency: 'DKK',
    status: 'ai_categorized',
    level_1: 'Facilities',
    level_2: 'Furniture',
    level_3: 'Office chairs',
    account_code: '6100',
    account_name: 'Office equipment',
    confidence: '0.62',
    rationale: 'Matched on "chair" against the Furniture spend-tree node.',
    // A categorized line points at the node it was categorized to. Null here
    // with levels set is the *stale* shape, which several tests below assert
    // on explicitly — so the ordinary fixture must not accidentally be it.
    spend_category_id: 'cat-chairs',
    level_4: null,
    category_stale: false,
    needs_review: false,
    verified_fields: [],
    ...overrides,
  }
}

const base = {
  currency: 'DKK',
  nodes: TREE_NODES,
  canManage: true,
  onVerify: () => Promise.resolve(),
  onUpdate: () => Promise.resolve(),
}


describe('the AI rationale', () => {
  it('is shown for a line the AI decided', () => {
    render(
      <LineEditor
        {...base}
        line={line({ status: 'ai_categorized', rationale: 'A commuter rail ticket.' })}
      />,
    )

    expect(screen.getByText('A commuter rail ticket.')).toBeTruthy()
  })

  it('is not shown for a line waiting to be categorized', () => {
    // A rationale explains a decision. An `uncategorized` line has none — it is
    // queued — so presenting one reads as a fresh verdict on a question that has
    // not been asked yet. That is exactly how a requeued line went on showing
    // the reasoning of the categorizer it was requeued away from.
    render(
      <LineEditor
        {...base}
        line={line({ status: 'uncategorized', rationale: 'Impossible to categorize.' })}
      />,
    )

    expect(screen.queryByText('Impossible to categorize.')).toBeNull()
  })

  it('is still shown for a genuine failure', () => {
    // `ai_failed` is a decision too — the model answered with something we never
    // offered — and the reason is the only account of it.
    render(
      <LineEditor
        {...base}
        line={line({ status: 'ai_failed', rationale: 'Chose 7 of 5 candidates.' })}
      />,
    )

    expect(screen.getByText('Chose 7 of 5 candidates.')).toBeTruthy()
  })
})
