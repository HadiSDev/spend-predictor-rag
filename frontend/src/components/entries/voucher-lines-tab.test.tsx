import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { VoucherLinesTab } from './voucher-lines-tab'
import type { InvoiceDetailRead, InvoiceLineRead } from '#/lib/types'

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
    ...overrides,
  }
}

/** An invoice posted by the ERP — evidence, never correctable at the header. */
function invoice(overrides: Partial<InvoiceDetailRead> = {}): InvoiceDetailRead {
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
    error_message: null,
    file_id: null,
    file_name: null,
    has_document: false,
    doc_status: 'not_applicable',
    doc_error: null,
    doc_processed_at: null,
    lines: [line()],
    ...overrides,
  }
}

const erpInvoice = invoice()

describe('VoucherLinesTab', () => {
  it('does not resend a category reselected back to the line\u2019s own', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(<VoucherLinesTab invoice={erpInvoice} onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES} />)

    // Search rather than drill: it reaches a leaf in one step, and the results
    // list identifies each node by its full path.
    fireEvent.click(screen.getByRole('button', { name: /office chairs/i }))
    fireEvent.change(await screen.findByLabelText(/search all categories/i), {
      target: { value: 'Office chairs' },
    })
    // The trigger reads as its own full path too, so scope to the popup's list.
    const results = await screen.findAllByRole('button', { name: /Furniture.*Office chairs/ })
    fireEvent.click(results[results.length - 1])
    // Re-picking the line's own category is no net change, so this must record
    // as a plain verify, not an edit.
    fireEvent.click(screen.getByRole('button', { name: /^accept$/i }))

    await waitFor(() => expect(onVerifyLine).toHaveBeenCalledWith('l2', {}))
  })

  it('submits the chosen node, not typed levels', async () => {
    // The whole point of the selector: a correction names a node, and the
    // server derives the levels from its path. Typed levels could name a
    // category that resolves to nothing.
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(<VoucherLinesTab invoice={erpInvoice} onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES} />)

    fireEvent.click(screen.getByRole('button', { name: /choose a category|office chairs/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^Facilities$/ }))
    fireEvent.click(await screen.findByRole('button', { name: /use this category/i }))
    fireEvent.click(screen.getByRole('button', { name: /save & verify/i }))

    await waitFor(() =>
      expect(onVerifyLine).toHaveBeenCalledWith('l2', { spend_category_id: 'n1' }),
    )
  })

  it('offers no free-text level inputs', () => {
    render(<VoucherLinesTab invoice={erpInvoice} onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES} />)
    expect(screen.queryByLabelText(/level 1/i)).toBeNull()
    expect(screen.queryByLabelText(/level 2/i)).toBeNull()
    expect(screen.queryByLabelText(/level 3/i)).toBeNull()
    expect(screen.queryByLabelText(/level 4/i)).toBeNull()
  })

  it('renders confidence as text, never colour alone', () => {
    render(
      <VoucherLinesTab
        invoice={invoice({ lines: [line({ confidence: '0.62' })] })}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.getByText(/62%/)).toBeTruthy()
  })

  it('sends an empty corrections object on a plain accept, so it records as a verify', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(<VoucherLinesTab invoice={erpInvoice} onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES} />)

    fireEvent.click(screen.getByRole('button', { name: /accept/i }))

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
    render(<VoucherLinesTab invoice={erpInvoice} onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES} />)

    fireEvent.click(screen.getByRole('button', { name: /accept/i }))

    const button = await screen.findByRole('button', { name: /accepting/i })
    expect(button).toHaveProperty('disabled', true)

    resolve()
    await waitFor(() => expect(screen.getByRole('button', { name: /^accept$/i })).toBeTruthy())
  })

  it('resets the chosen category without submitting when cancelled', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(<VoucherLinesTab invoice={erpInvoice} onVerifyLine={onVerifyLine}
        spendTreeNodes={TREE_NODES} />)

    fireEvent.click(screen.getByRole('button', { name: /office chairs/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^Facilities$/ }))
    fireEvent.click(await screen.findByRole('button', { name: /use this category/i }))
    expect(screen.getByRole('button', { name: /save & verify/i })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    // Back to the line's own category, and nothing was sent.
    expect(screen.getByRole('button', { name: /office chairs/i })).toBeTruthy()
    expect(onVerifyLine).not.toHaveBeenCalled()
  })

  it('says so, and links out, when the company has no spend tree', () => {
    render(
      <VoucherLinesTab
        invoice={erpInvoice}
        onVerifyLine={vi.fn()}
        spendTreeNodes={[]}
        companySettingsHref="/settings/companies"
      />,
    )
    expect(screen.getByText(/no spend tree is assigned/i)).toBeTruthy()
    expect(screen.getByRole('link', { name: /company settings/i })).toBeTruthy()
    // The evidence stays readable; only the picker is withheld.
    expect(screen.getByText(/matched on "chair"/i)).toBeTruthy()
  })

  it('marks a line whose category no longer resolves as needing review', () => {
    render(
      <VoucherLinesTab
        invoice={invoice({
          lines: [line({ spend_category_id: null, category_stale: true })],
        })}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.getByText(/needs review/i)).toBeTruthy()
    // Distinct from a failure: nothing failed, the taxonomy moved.
    expect(screen.queryByText(/categorization failed/i)).toBeNull()
    // The previous decision stays visible — it is the reviewer's only clue.
    // Shown both on the trigger and in the explanation beneath it.
    expect(screen.getAllByText(/Facilities › Furniture › Office chairs/).length).toBeGreaterThan(0)
  })

  it('renders the rationale de-emphasised, distinct from the editable fields', () => {
    render(<VoucherLinesTab invoice={erpInvoice} onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES} />)
    expect(screen.getByText(/matched on "chair"/i)).toBeTruthy()
  })

  it('renders every line, each with its own editor', () => {
    render(
      <VoucherLinesTab
        invoice={invoice({
          lines: [line({ id: 'l2' }), line({ id: 'l3', description: 'Standing desk' })],
        })}
        onVerifyLine={vi.fn()}
        spendTreeNodes={TREE_NODES}
      />,
    )
    expect(screen.getAllByRole('button', { name: /^accept$/i })).toHaveLength(2)
    expect(screen.getByText('Standing desk')).toBeTruthy()
  })
})
