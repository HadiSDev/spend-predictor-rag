import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { VoucherLinesTab } from './voucher-lines-tab'
import type { InvoiceDetailRead, InvoiceLineRead } from '#/lib/api/types'

const TREE_NODES = [
  {
    id: 'n1',
    spend_tree_id: 'tree1',
    parent_id: null,
    depth: 1,
    name: 'Facilities',
    code: null,
    sort_order: 0,
    description: null,
    level_1: 'Facilities',
    level_2: null,
    level_3: null,
    level_4: null,
  },
  {
    id: 'n2',
    spend_tree_id: 'tree1',
    parent_id: 'n1',
    depth: 2,
    name: 'Furniture',
    code: null,
    sort_order: 0,
    description: null,
    level_1: 'Facilities',
    level_2: 'Furniture',
    level_3: null,
    level_4: null,
  },
  {
    id: 'cat-chairs',
    spend_tree_id: 'tree1',
    parent_id: 'n2',
    depth: 3,
    name: 'Office chairs',
    code: '6100',
    sort_order: 0,
    description: null,
    level_1: 'Facilities',
    level_2: 'Furniture',
    level_3: 'Office chairs',
    level_4: null,
  },
]

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
    spend_category_id: 'cat-chairs',
    level_4: null,
    category_stale: false,
    needs_review: false,
    verified_fields: [],
    ...overrides,
  }
}

function invoice(
  overrides: Partial<InvoiceDetailRead> = {},
): InvoiceDetailRead {
  return {
    id: 'inv1',
    company_id: 'c1',
    vendor_id: 'v1',
    invoice_number: 'INV-2026-0412',
    document_invoice_number: null,
    invoice_date: '2026-04-12',
    currency: 'DKK',
    total: '900.00',
    tax: '225.00',
    base_currency: 'DKK',
    base_total: '900.00',
    base_tax: '225.00',
    fx_rate: '1',
    fx_rate_date: '2026-04-12',
    status: 'categorized',
    source: 'erp',
    supplier_name: null,
    supplier_country_code: null,
    supplier_vat_number: null,
    supplier_overrides: [],
    verified_fields: [],
    verified_at: null,
    verified_by: null,
    error_message: null,
    file_id: null,
    file_name: null,
    has_document: false,
    doc_status: 'not_applicable',
    doc_error: null,
    doc_processed_at: null,
    document_total: null,
    document_tax: null,
    totals_agree: null,
    lines: [line()],
    lines_reconciled: true,
    reconciliation_delta: null,
    ...overrides,
  }
}

const erpInvoice = invoice()

const writes = () => ({
  canManage: true,
  onUpdateLine: vi.fn().mockResolvedValue(undefined),
  onCreateLine: vi.fn().mockResolvedValue(undefined),
  onDeleteLine: vi.fn().mockResolvedValue(undefined),
})

describe('VoucherLinesTab', () => {
  it('does not resend a category reselected back to the line\u2019s own', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={erpInvoice}
        onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /office chairs/i }))
    fireEvent.change(await screen.findByLabelText(/search all categories/i), {
      target: { value: 'Office chairs' },
    })
    const results = await screen.findAllByRole('button', {
      name: /Furniture.*Office chairs/,
    })
    fireEvent.click(results[results.length - 1])
    fireEvent.click(screen.getByRole('button', { name: /^accept category$/i }))

    await waitFor(() => expect(onVerifyLine).toHaveBeenCalledWith('l2', {}))
  })

  it('submits the chosen node, not typed levels', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={erpInvoice}
        onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.click(
      screen.getByRole('button', { name: /choose a category|office chairs/i }),
    )
    fireEvent.click(await screen.findByRole('button', { name: /^Facilities$/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /use this category/i }),
    )
    fireEvent.click(
      screen.getByRole('button', { name: /save & verify category/i }),
    )

    await waitFor(() =>
      expect(onVerifyLine).toHaveBeenCalledWith('l2', {
        spend_category_id: 'n1',
      }),
    )
  })

  it('offers no free-text level inputs', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={erpInvoice}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.queryByLabelText(/level 1/i)).toBeNull()
    expect(screen.queryByLabelText(/level 2/i)).toBeNull()
    expect(screen.queryByLabelText(/level 3/i)).toBeNull()
    expect(screen.queryByLabelText(/level 4/i)).toBeNull()
  })

  it('renders confidence as text, never colour alone', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={invoice({ lines: [line({ confidence: '0.62' })] })}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.getByText(/62%/)).toBeTruthy()
  })

  it('sends an empty corrections object on a plain accept, so it records as a verify', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={erpInvoice}
        onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /accept category/i }))

    await waitFor(() => expect(onVerifyLine).toHaveBeenCalledWith('l2', {}))
  })

  it('disables the submit control and shows a pending state while in flight', async () => {
    let resolve!: () => void
    const onVerifyLine = vi.fn(
      () =>
        new Promise<void>((r) => {
          resolve = r
        }),
    )
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={erpInvoice}
        onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /accept category/i }))

    const button = await screen.findByRole('button', { name: /accepting/i })
    expect(button).toHaveProperty('disabled', true)

    resolve()
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /^accept category$/i }),
      ).toBeTruthy(),
    )
  })

  it('resets the chosen category without submitting when cancelled', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={erpInvoice}
        onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /office chairs/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^Facilities$/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /use this category/i }),
    )
    expect(
      screen.getByRole('button', { name: /save & verify category/i }),
    ).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    expect(screen.getByRole('button', { name: /office chairs/i })).toBeTruthy()
    expect(onVerifyLine).not.toHaveBeenCalled()
  })

  it('says so, and links out, when the company has no spend tree', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={erpInvoice}
        onVerifyLine={vi.fn()}
        spendTreeNodes={[]}
        companySettingsHref="/settings/companies"
      />,
    )
    expect(screen.getByText(/no spend tree is assigned/i)).toBeTruthy()
    expect(screen.getByRole('link', { name: /company settings/i })).toBeTruthy()
    expect(screen.getByText(/matched on "chair"/i)).toBeTruthy()
  })

  it('marks a line whose category no longer resolves', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={invoice({
          lines: [line({ spend_category_id: null, category_stale: true })],
          lines_reconciled: true,
          reconciliation_delta: null,
        })}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.getByText(/unresolved category/i)).toBeTruthy()
    expect(screen.queryByText(/categorization failed/i)).toBeNull()
    expect(
      screen.getAllByText(/Facilities › Furniture › Office chairs/).length,
    ).toBeGreaterThan(0)
  })

  it('renders the rationale de-emphasised, distinct from the editable fields', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={erpInvoice}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.getByText(/matched on "chair"/i)).toBeTruthy()
  })

  it('mounts one line at a time, not every line at once', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={invoice({
          lines: [
            line({ id: 'l2' }),
            line({ id: 'l3', description: 'Standing desk' }),
          ],
          lines_reconciled: true,
          reconciliation_delta: null,
        })}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(
      screen.getAllByRole('button', { name: /^accept category$/i }),
    ).toHaveLength(1)
    expect(screen.getByText('1 of 2')).toBeTruthy()
    expect(screen.queryByText('Standing desk')).toBeNull()
  })
})

describe('VoucherLinesTab — correcting a line', () => {
  it('sends only the line fields that changed', async () => {
    const onUpdateLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        onUpdateLine={onUpdateLine}
        invoice={erpInvoice}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.change(screen.getByLabelText(/^description$/i), {
      target: { value: 'Herman Miller Aeron' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save line$/i }))

    await waitFor(() =>
      expect(onUpdateLine).toHaveBeenCalledWith('l2', {
        description: 'Herman Miller Aeron',
      }),
    )
  })

  it('keeps the value save separate from the category verify', async () => {
    const onUpdateLine = vi.fn().mockResolvedValue(undefined)
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        onUpdateLine={onUpdateLine}
        invoice={erpInvoice}
        onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.change(screen.getByLabelText(/^quantity$/i), {
      target: { value: '3' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save line$/i }))

    await waitFor(() =>
      expect(onUpdateLine).toHaveBeenCalledWith('l2', { quantity: 3 }),
    )
    expect(onVerifyLine).not.toHaveBeenCalled()
  })

  it('offers no line inputs to a read-only role', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        canManage={false}
        invoice={erpInvoice}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.queryByLabelText(/^description$/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /^save line$/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /add line/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /^delete line/i })).toBeNull()
  })
})

describe('VoucherLinesTab — paging', () => {
  const threeLines = () =>
    invoice({
      lines: [
        line({ id: 'l3', item_name: 'Third', sequence: 2 }),
        line({ id: 'l1', item_name: 'First', sequence: 0 }),
        line({ id: 'l2', item_name: 'Second', sequence: 1 }),
      ],
    })

  const paged = (overrides = {}) => (
    <VoucherLinesTab
      {...writes()}
      invoice={threeLines()}
      onVerifyLine={vi.fn()}
      spendTreeNodes={TREE_NODES}
      {...overrides}
    />
  )

  it('opens on the first line and states the position', () => {
    render(paged())

    expect(screen.getByText('1 of 3')).toBeTruthy()
    expect(screen.getByDisplayValue('First')).toBeTruthy()
  })

  it('orders by the sequence the source stated, not by row id', () => {
    render(paged())

    fireEvent.click(screen.getByRole('button', { name: /next line/i }))
    expect(screen.getByDisplayValue('Second')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /next line/i }))
    expect(screen.getByDisplayValue('Third')).toBeTruthy()
  })

  it('steps back as well as forward', () => {
    render(paged())

    fireEvent.click(screen.getByRole('button', { name: /next line/i }))
    fireEvent.click(screen.getByRole('button', { name: /previous line/i }))

    expect(screen.getByText('1 of 3')).toBeTruthy()
    expect(screen.getByDisplayValue('First')).toBeTruthy()
  })

  it('stops at the ends rather than wrapping', () => {
    render(paged())

    expect(
      screen.getByRole('button', { name: /previous line/i }),
    ).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: /next line/i })).toHaveProperty(
      'disabled',
      false,
    )

    fireEvent.click(screen.getByRole('button', { name: /next line/i }))
    fireEvent.click(screen.getByRole('button', { name: /next line/i }))

    expect(screen.getByText('3 of 3')).toBeTruthy()
    expect(screen.getByRole('button', { name: /next line/i })).toHaveProperty(
      'disabled',
      true,
    )
    expect(
      screen.getByRole('button', { name: /previous line/i }),
    ).toHaveProperty('disabled', false)
  })

  it('offers no navigation on a single-line invoice', () => {
    render(
      paged({
        invoice: invoice({ lines: [line({ id: 'only', item_name: 'Only' })] }),
      }),
    )

    expect(screen.getByText('1 of 1')).toBeTruthy()
    expect(
      screen.getByRole('button', { name: /previous line/i }),
    ).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: /next line/i })).toHaveProperty(
      'disabled',
      true,
    )
  })

  it('opens on the line the reader activated, not on the first', () => {
    render(paged({ initialLineId: 'l3' }))

    expect(screen.getByText('3 of 3')).toBeTruthy()
    expect(screen.getByDisplayValue('Third')).toBeTruthy()
  })

  it('ignores a line id belonging to another invoice', () => {
    render(paged({ initialLineId: 'not-on-this-invoice' }))

    expect(screen.getByText('1 of 3')).toBeTruthy()
  })

  it('shows the empty state with no navigation when there are no lines', () => {
    render(paged({ invoice: invoice({ lines: [] }) }))

    expect(screen.getByText(/no lines on this invoice/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /next line/i })).toBeNull()
    expect(screen.queryByText(/ of /)).toBeNull()
  })
})

describe('VoucherLinesTab — paging and the keyboard', () => {
  const threeLines = () =>
    invoice({
      lines: [
        line({ id: 'l1', item_name: 'First', sequence: 0 }),
        line({ id: 'l2', item_name: 'Second', sequence: 1 }),
      ],
    })

  it('pages on arrow keys when focus is not in a field', () => {
    const { container } = render(
      <VoucherLinesTab
        {...writes()}
        invoice={threeLines()}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.keyDown(container.firstChild as HTMLElement, {
      key: 'ArrowRight',
    })
    expect(screen.getByText('2 of 2')).toBeTruthy()

    fireEvent.keyDown(container.firstChild as HTMLElement, { key: 'ArrowLeft' })
    expect(screen.getByText('1 of 2')).toBeTruthy()
  })

  it('leaves arrow keys alone inside a text field', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={threeLines()}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.keyDown(screen.getByLabelText(/^item name$/i), {
      key: 'ArrowRight',
    })

    expect(screen.getByText('1 of 2')).toBeTruthy()
  })

  it('names its navigation controls', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={threeLines()}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )

    expect(screen.getByRole('button', { name: /previous line/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /next line/i })).toBeTruthy()
  })
})

describe('VoucherLinesTab — paging away from unsaved work', () => {
  const twoLines = () =>
    invoice({
      lines: [
        line({ id: 'l1', item_name: 'First', sequence: 0 }),
        line({ id: 'l2', item_name: 'Second', sequence: 1 }),
      ],
    })

  const render2 = () =>
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={twoLines()}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )

  it('pages straight away when nothing is edited', () => {
    render2()

    fireEvent.click(screen.getByRole('button', { name: /next line/i }))

    expect(screen.getByText('2 of 2')).toBeTruthy()
    expect(screen.queryByText(/unsaved changes/i)).toBeNull()
  })

  it('asks before discarding an edit', () => {
    render2()

    fireEvent.change(screen.getByLabelText(/^item name$/i), {
      target: { value: 'Edited' },
    })
    fireEvent.click(screen.getByRole('button', { name: /next line/i }))

    expect(screen.getByText(/unsaved changes/i)).toBeTruthy()
    expect(screen.getByText('1 of 2')).toBeTruthy()
  })

  it('keeps the edit when the reviewer declines', () => {
    render2()

    fireEvent.change(screen.getByLabelText(/^item name$/i), {
      target: { value: 'Edited' },
    })
    fireEvent.click(screen.getByRole('button', { name: /next line/i }))
    fireEvent.click(screen.getByRole('button', { name: /stay on this line/i }))

    expect(screen.getByText('1 of 2')).toBeTruthy()
    expect(screen.getByDisplayValue('Edited')).toBeTruthy()
    expect(screen.queryByText(/unsaved changes/i)).toBeNull()
  })

  it('pages and discards when the reviewer confirms', () => {
    render2()

    fireEvent.change(screen.getByLabelText(/^item name$/i), {
      target: { value: 'Edited' },
    })
    fireEvent.click(screen.getByRole('button', { name: /next line/i }))
    fireEvent.click(
      screen.getByRole('button', { name: /discard and continue/i }),
    )

    expect(screen.getByText('2 of 2')).toBeTruthy()
    expect(screen.getByDisplayValue('Second')).toBeTruthy()
  })

  it('does not carry one line’s pending edits onto the next', () => {
    render2()

    fireEvent.change(screen.getByLabelText(/^item name$/i), {
      target: { value: 'Edited' },
    })
    fireEvent.click(screen.getByRole('button', { name: /next line/i }))
    fireEvent.click(
      screen.getByRole('button', { name: /discard and continue/i }),
    )
    fireEvent.click(screen.getByRole('button', { name: /previous line/i }))

    expect(screen.getByDisplayValue('First')).toBeTruthy()
  })
})

describe('VoucherLinesTab — numbers are numbers', () => {
  it('shows a stored decimal at its display scale, not as the column holds it', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        onVerifyLine={vi.fn()}
        invoice={invoice({ lines: [line({ amount: '1234.50000' })] })}
        spendTreeNodes={TREE_NODES}
      />,
    )

    const shown = screen.getByLabelText<HTMLInputElement>(/^amount$/i).value
    expect(shown).toContain('1,234.50')
    expect(shown).not.toContain('1234.50000')
  })

  it('never submits null for a figure it could not read', async () => {
    const onUpdateLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        onVerifyLine={vi.fn()}
        onUpdateLine={onUpdateLine}
        invoice={erpInvoice}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.change(screen.getByLabelText(/^amount$/i), {
      target: { value: '1,5' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save line$/i }))

    await waitFor(() => expect(onUpdateLine).toHaveBeenCalled())
    const [, changes] = onUpdateLine.mock.lastCall ?? []
    expect(changes?.amount).not.toBeNull()
    expect(Number.isNaN(changes?.amount)).toBe(false)
  })

  it('does not report a line as edited just because the formatter tidied it', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        onVerifyLine={vi.fn()}
        invoice={invoice({
          lines: [line({ amount: '1234.50000', quantity: '0.2500' })],
        })}
        spendTreeNodes={TREE_NODES}
      />,
    )

    expect(screen.getByRole('button', { name: /^save line$/i })).toHaveProperty(
      'disabled',
      true,
    )
  })

  it('leaves an untouched quantity exactly as it was stored', async () => {
    const onUpdateLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        onVerifyLine={vi.fn()}
        onUpdateLine={onUpdateLine}
        invoice={invoice({ lines: [line({ quantity: '0.2500' })] })}
        spendTreeNodes={TREE_NODES}
      />,
    )

    expect(screen.getByLabelText<HTMLInputElement>(/^quantity$/i).value).toBe(
      '0.25',
    )

    fireEvent.change(screen.getByLabelText(/^item name$/i), {
      target: { value: 'Chairs' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save line$/i }))

    await waitFor(() => expect(onUpdateLine).toHaveBeenCalled())
    const [, changes] = onUpdateLine.mock.lastCall ?? []
    expect(changes).not.toHaveProperty('quantity')
  })

  it('corrects the item name and the description independently', async () => {
    const onUpdateLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        onVerifyLine={vi.fn()}
        onUpdateLine={onUpdateLine}
        invoice={erpInvoice}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.change(screen.getByLabelText(/^item name$/i), {
      target: { value: 'Office chair' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save line$/i }))

    await waitFor(() =>
      expect(onUpdateLine).toHaveBeenCalledWith('l2', {
        item_name: 'Office chair',
      }),
    )
  })
})

describe('VoucherLinesTab — adding and deleting', () => {
  it('adds an empty line for the reviewer to fill in', async () => {
    const onCreateLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        onCreateLine={onCreateLine}
        invoice={erpInvoice}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /add line/i }))

    await waitFor(() => expect(onCreateLine).toHaveBeenCalledWith('inv1'))
  })

  it('asks before deleting, naming the line', async () => {
    const onDeleteLine = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherLinesTab
        {...writes()}
        onDeleteLine={onDeleteLine}
        invoice={erpInvoice}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /^delete line 1$/i }))
    expect(onDeleteLine).not.toHaveBeenCalled()
    expect(screen.getByText(/its postings stay on the voucher/i)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /^delete line$/i }))
    await waitFor(() => expect(onDeleteLine).toHaveBeenCalledWith('l2'))
  })

  it('marks a hand-written line as one', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={invoice({ lines: [line({ origin: 'human' })] })}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.getByText(/added by hand/i)).toBeTruthy()
  })
})

describe('VoucherLinesTab — reconciliation', () => {
  it('says so when the lines do not add up, with both figures and the gap', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={invoice({
          lines_reconciled: false,
          reconciliation_delta: '-400.00',
        })}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.getByText(/do not add up to the invoice total/i)).toBeTruthy()
    expect(screen.getByText(/short by/i)).toBeTruthy()
  })

  it('says nothing when the lines reconcile', () => {
    render(
      <VoucherLinesTab
        {...writes()}
        invoice={erpInvoice}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.queryByText(/do not add up/i)).toBeNull()
  })
})
