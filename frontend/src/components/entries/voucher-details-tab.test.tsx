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
    unit_price: '450.00',
    amount: '900.00',
    native_account_code: null,
    base_currency: 'DKK',
    base_amount: '900.00',
    fx_rate: '1',
    fx_rate_date: '2026-04-12',
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
    lines: [line()],
    ...overrides,
  }
}

const erpInvoice = invoice()

describe('VoucherDetailsTab', () => {
  it('renders ERP header values as evidence, not as inputs', () => {
    // Provenance decides affordance. A disabled input still reads as tappable.
    render(<VoucherDetailsTab invoice={erpInvoice} onVerifyLine={vi.fn()} />)
    expect(screen.getByText('INV-2026-0412')).toBeTruthy()
    expect(screen.queryByLabelText(/invoice number/i)).toBeNull()
  })

  it('carries the ERP provenance as text, not colour alone', () => {
    render(<VoucherDetailsTab invoice={erpInvoice} onVerifyLine={vi.fn()} />)
    expect(screen.getByText(/erp posting/i)).toBeTruthy()
  })

  it('lets a parsed header be corrected', () => {
    render(
      <VoucherDetailsTab
        invoice={{ ...erpInvoice, source: 'pdf_extraction' }}
        onVerifyLine={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/invoice number/i)).toBeTruthy()
    expect(screen.getByText(/pdf extraction/i)).toBeTruthy()
  })

  it('submits a corrected category and shows the confidence being judged', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab invoice={erpInvoice} onVerifyLine={onVerifyLine} />)

    fireEvent.change(screen.getByLabelText(/level 2/i), { target: { value: 'Office supplies' } })
    fireEvent.click(screen.getByRole('button', { name: /accept/i }))

    await waitFor(() =>
      expect(onVerifyLine).toHaveBeenCalledWith('l2', { level_2: 'Office supplies' }),
    )
  })

  it('renders confidence as text, never colour alone', () => {
    render(
      <VoucherDetailsTab
        invoice={invoice({ lines: [line({ confidence: '0.62' })] })}
        onVerifyLine={vi.fn()}
      />,
    )
    expect(screen.getByText(/62%/)).toBeTruthy()
  })

  it('sends an empty corrections object on a plain accept, so it records as a verify', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab invoice={erpInvoice} onVerifyLine={onVerifyLine} />)

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
    render(<VoucherDetailsTab invoice={erpInvoice} onVerifyLine={onVerifyLine} />)

    fireEvent.click(screen.getByRole('button', { name: /accept/i }))

    const button = await screen.findByRole('button', { name: /accepting/i })
    expect(button).toHaveProperty('disabled', true)

    resolve()
    await waitFor(() => expect(screen.getByRole('button', { name: /^accept$/i })).toBeTruthy())
  })

  it('resets edits without submitting when cancelled', () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab invoice={erpInvoice} onVerifyLine={onVerifyLine} />)

    const level2 = screen.getByLabelText<HTMLInputElement>(/level 2/i)
    fireEvent.change(level2, { target: { value: 'Office supplies' } })
    expect(level2.value).toBe('Office supplies')

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    expect(screen.getByLabelText<HTMLInputElement>(/level 2/i).value).toBe('Furniture')
    expect(onVerifyLine).not.toHaveBeenCalled()
  })

  it('renders the rationale de-emphasised, distinct from the editable fields', () => {
    render(<VoucherDetailsTab invoice={erpInvoice} onVerifyLine={vi.fn()} />)
    expect(screen.getByText(/matched on "chair"/i)).toBeTruthy()
  })

  it('renders every line, each with its own editor', () => {
    render(
      <VoucherDetailsTab
        invoice={invoice({
          lines: [line({ id: 'l2' }), line({ id: 'l3', description: 'Standing desk' })],
        })}
        onVerifyLine={vi.fn()}
      />,
    )
    expect(screen.getAllByRole('button', { name: /^accept$/i })).toHaveLength(2)
    expect(screen.getByText('Standing desk')).toBeTruthy()
  })
})
