import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { VoucherDetailsTab } from './voucher-details-tab'
import type { InvoiceDetailRead, InvoiceLineRead } from '#/lib/types'

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
    spend_category_id: null,
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

describe('VoucherDetailsTab', () => {
  it('renders ERP header values as evidence, not as inputs', () => {
    // Provenance decides affordance. A disabled input still reads as tappable.
    render(<VoucherDetailsTab invoice={erpInvoice} canRetrigger onReprocess={vi.fn().mockResolvedValue(undefined)} onUpdateHeader={vi.fn().mockResolvedValue(undefined)} />)
    expect(screen.getByText('INV-2026-0412')).toBeTruthy()
    expect(screen.queryByLabelText(/invoice number/i)).toBeNull()
  })

  it('carries the ERP provenance as text, not colour alone', () => {
    render(<VoucherDetailsTab invoice={erpInvoice} canRetrigger onReprocess={vi.fn().mockResolvedValue(undefined)} onUpdateHeader={vi.fn().mockResolvedValue(undefined)} />)
    expect(screen.getByText(/erp posting/i)).toBeTruthy()
  })

  it('lets a parsed header be corrected', () => {
    render(
      <VoucherDetailsTab
        invoice={{ ...erpInvoice, source: 'pdf_extraction' }}
        canRetrigger
        onReprocess={vi.fn().mockResolvedValue(undefined)}
        onUpdateHeader={vi.fn().mockResolvedValue(undefined)}
      />,
    )
    expect(screen.getByLabelText(/invoice number/i)).toBeTruthy()
    expect(screen.getByText(/pdf extraction/i)).toBeTruthy()
  })

  it('saves only the header fields that changed', async () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    const parsed = invoice({ source: 'pdf_extraction' })
    render(
      <VoucherDetailsTab invoice={parsed} canRetrigger onReprocess={vi.fn().mockResolvedValue(undefined)} onUpdateHeader={onUpdateHeader} />,
    )

    fireEvent.change(screen.getByLabelText(/invoice number/i), { target: { value: 'INV-CORRECTED' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(onUpdateHeader).toHaveBeenCalledWith(parsed.id, { invoice_number: 'INV-CORRECTED' }),
    )
  })

  it('disables save and cancel until the header has an edit', () => {
    render(
      <VoucherDetailsTab
        invoice={invoice({ source: 'pdf_extraction' })}
        canRetrigger
        onReprocess={vi.fn().mockResolvedValue(undefined)}
        onUpdateHeader={vi.fn().mockResolvedValue(undefined)}
      />,
    )
    // "Cancel" is ambiguous with the line editor's own Cancel button below —
    // the header's is the first of the two in document order.
    expect(screen.getByRole('button', { name: /^save$/i })).toHaveProperty('disabled', true)
    expect(screen.getAllByRole('button', { name: /^cancel$/i })[0]).toHaveProperty('disabled', true)
  })

  it('resets the header without saving when cancelled', () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    render(
      <VoucherDetailsTab
        invoice={invoice({ source: 'pdf_extraction' })}
        canRetrigger
        onReprocess={vi.fn().mockResolvedValue(undefined)}
        onUpdateHeader={onUpdateHeader}
      />,
    )

    const field = screen.getByLabelText<HTMLInputElement>(/invoice number/i)
    fireEvent.change(field, { target: { value: 'INV-DRAFT' } })
    fireEvent.click(screen.getAllByRole('button', { name: /^cancel$/i })[0])

    expect(screen.getByLabelText<HTMLInputElement>(/invoice number/i).value).toBe('INV-2026-0412')
    expect(onUpdateHeader).not.toHaveBeenCalled()
  })

  it('surfaces a save failure rather than swallowing it', async () => {
    const onUpdateHeader = vi.fn().mockRejectedValue(new Error('boom'))
    render(
      <VoucherDetailsTab
        invoice={invoice({ source: 'pdf_extraction' })}
        canRetrigger
        onReprocess={vi.fn().mockResolvedValue(undefined)}
        onUpdateHeader={onUpdateHeader}
      />,
    )

    fireEvent.change(screen.getByLabelText(/invoice number/i), { target: { value: 'INV-BAD' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByText(/boom/i)).toBeTruthy()
  })

  it('reports the header dirty while an edit is uncommitted, and clean again once saved', async () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    const onHeaderDirtyChange = vi.fn()
    render(
      <VoucherDetailsTab
        invoice={invoice({ source: 'pdf_extraction' })}
        canRetrigger
        onReprocess={vi.fn().mockResolvedValue(undefined)}
        onUpdateHeader={onUpdateHeader}
        onHeaderDirtyChange={onHeaderDirtyChange}
      />,
    )
    expect(onHeaderDirtyChange).toHaveBeenLastCalledWith(false)

    fireEvent.change(screen.getByLabelText(/invoice number/i), { target: { value: 'INV-DRAFT' } })
    expect(onHeaderDirtyChange).toHaveBeenLastCalledWith(true)

    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(onHeaderDirtyChange).toHaveBeenLastCalledWith(false))
  })

  it('never renders save/cancel controls for an ERP-sourced header, which is not editable', () => {
    render(
      <VoucherDetailsTab invoice={erpInvoice} canRetrigger onReprocess={vi.fn().mockResolvedValue(undefined)} onUpdateHeader={vi.fn()} />,
    )
    expect(screen.queryByRole('button', { name: /^save$/i })).toBeNull()
  })

  it('tracks the invoice prop rather than only its value at mount', () => {
    // A drawer that stays mounted while the selected voucher changes must not
    // leave a parsed header showing the previous invoice's values.
    const invoiceA = invoice({
      id: 'inv-a',
      source: 'pdf_extraction',
      invoice_number: 'INV-A',
    })
    const invoiceB = invoice({
      id: 'inv-b',
      source: 'pdf_extraction',
      invoice_number: 'INV-B',
    })

    const { rerender } = render(
      <VoucherDetailsTab invoice={invoiceA} canRetrigger onReprocess={vi.fn().mockResolvedValue(undefined)} onUpdateHeader={vi.fn().mockResolvedValue(undefined)} />,
    )
    expect(screen.getByLabelText<HTMLInputElement>(/invoice number/i).value).toBe('INV-A')

    rerender(<VoucherDetailsTab invoice={invoiceB} canRetrigger onReprocess={vi.fn().mockResolvedValue(undefined)} onUpdateHeader={vi.fn().mockResolvedValue(undefined)} />)
    expect(screen.getByLabelText<HTMLInputElement>(/invoice number/i).value).toBe('INV-B')
  })
})
