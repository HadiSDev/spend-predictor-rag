import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { VoucherDetailsTab } from './voucher-details-tab'
import type { VoucherDetailsTabProps } from './voucher-details-tab'
import type { InvoiceDetailRead, InvoiceLineRead } from '#/lib/api/types'

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

function props(
  overrides: Partial<VoucherDetailsTabProps> = {},
): VoucherDetailsTabProps {
  return {
    invoice: erpInvoice,
    canManage: true,
    vendors: [],
    onReprocess: vi.fn().mockResolvedValue(undefined),
    onUpdateHeader: vi.fn().mockResolvedValue(undefined),
    onVerifyHeader: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('VoucherDetailsTab', () => {
  it('shows a totals disagreement to a manager and a viewer alike', () => {
    const disagreeing = invoice({
      document_total: '104.85',
      document_tax: '20.97',
      totals_agree: false,
    })

    const manager = render(
      <VoucherDetailsTab {...props({ invoice: disagreeing })} />,
    )
    expect(screen.getByRole('note').textContent).toContain('104.85')
    manager.unmount()

    render(
      <VoucherDetailsTab
        {...props({ invoice: disagreeing, canManage: false })}
      />,
    )
    expect(screen.getByRole('note').textContent).toContain('104.85')
  })

  it('shows no second total when the two agree', () => {
    render(
      <VoucherDetailsTab
        {...props({
          invoice: invoice({ document_total: '900.00', totals_agree: true }),
        })}
      />,
    )
    expect(screen.queryByRole('note')).toBeNull()
  })

  it('lets a manager correct an ERP-sourced header', () => {
    render(<VoucherDetailsTab {...props()} />)
    expect(screen.getByLabelText(/invoice number/i)).toBeTruthy()
  })

  it('shows a read-only role evidence text, never a disabled input', () => {
    render(<VoucherDetailsTab {...props({ canManage: false })} />)
    expect(screen.getByText('INV-2026-0412')).toBeTruthy()
    expect(screen.queryByLabelText(/invoice number/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /^save$/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /verify header/i })).toBeNull()
  })

  it('carries the ERP provenance as text, not colour alone', () => {
    render(<VoucherDetailsTab {...props()} />)
    expect(screen.getByText(/erp posting/i)).toBeTruthy()
  })

  it('saves only the header fields that changed', async () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab {...props({ onUpdateHeader })} />)

    fireEvent.change(screen.getByLabelText(/invoice number/i), {
      target: { value: 'INV-CORRECTED' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(onUpdateHeader).toHaveBeenCalledWith(erpInvoice.id, {
        document_invoice_number: 'INV-CORRECTED',
      }),
    )
  })

  it('sends a supplier correction without touching the vendor link', async () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab {...props({ onUpdateHeader })} />)

    fireEvent.change(screen.getByLabelText(/vat number/i), {
      target: { value: 'DE123456789' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(onUpdateHeader).toHaveBeenCalledWith(erpInvoice.id, {
        supplier_vat_number: 'DE123456789',
      }),
    )
  })

  it('says a supplier correction applies to this invoice only', () => {
    render(<VoucherDetailsTab {...props()} />)
    expect(screen.getByText(/applies to this invoice only/i)).toBeTruthy()
  })

  it('marks a supplier value the invoice overrides', () => {
    render(
      <VoucherDetailsTab
        {...props({
          invoice: invoice({
            supplier_country_code: 'DE',
            supplier_overrides: ['supplier_country_code'],
          }),
        })}
      />,
    )
    expect(screen.getByText(/corrected/i)).toBeTruthy()
  })

  it('disables save and cancel until the header has an edit', () => {
    render(<VoucherDetailsTab {...props()} />)
    expect(screen.getByRole('button', { name: /^save$/i })).toHaveProperty(
      'disabled',
      true,
    )
    expect(screen.getByRole('button', { name: /^cancel$/i })).toHaveProperty(
      'disabled',
      true,
    )
  })

  it('offers verify even with nothing edited', () => {
    const onVerifyHeader = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab {...props({ onVerifyHeader })} />)

    const verify = screen.getByRole('button', { name: /verify header/i })
    expect(verify).toHaveProperty('disabled', false)
    fireEvent.click(verify)

    return waitFor(() =>
      expect(onVerifyHeader).toHaveBeenCalledWith(erpInvoice.id, {}),
    )
  })

  it('verifies the pending edit along with the verification', async () => {
    const onVerifyHeader = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab {...props({ onVerifyHeader })} />)

    fireEvent.change(screen.getByLabelText(/^tax$/i), {
      target: { value: '25' },
    })
    fireEvent.click(screen.getByRole('button', { name: /save and verify/i }))

    await waitFor(() =>
      expect(onVerifyHeader).toHaveBeenCalledWith(erpInvoice.id, { tax: 25 }),
    )
  })

  it('shows who verified the header and when', () => {
    render(
      <VoucherDetailsTab
        {...props({
          invoice: invoice({
            verified_at: '2026-05-01T10:00:00Z',
            verified_by: 'user-1',
            verified_fields: ['total'],
          }),
        })}
      />,
    )
    expect(screen.getByText(/verified/i)).toBeTruthy()
    expect(screen.getByText(/will not be overwritten by a sync/i)).toBeTruthy()
  })

  it('resets the header without saving when cancelled', () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    const scanned = invoice({ document_invoice_number: 'INV-2026-0412' })
    render(
      <VoucherDetailsTab {...props({ invoice: scanned, onUpdateHeader })} />,
    )

    fireEvent.change(screen.getByLabelText(/invoice number/i), {
      target: { value: 'INV-DRAFT' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }))

    expect(
      screen.getByLabelText<HTMLInputElement>(/invoice number/i).value,
    ).toBe('INV-2026-0412')
    expect(onUpdateHeader).not.toHaveBeenCalled()
  })

  it('picks a currency from the ISO list rather than accepting typed text', async () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab {...props({ onUpdateHeader })} />)

    const picker = screen.getByRole('combobox', { name: 'Currency' })
    fireEvent.click(picker)
    fireEvent.change(picker, { target: { value: 'EUR' } })
    fireEvent.click(await screen.findByRole('option', { name: /^EUR —/ }))

    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(onUpdateHeader).toHaveBeenCalledWith(erpInvoice.id, {
        currency: 'EUR',
      }),
    )
  })

  it('names the picker for the invoice, not for the company’s reporting currency', () => {
    render(<VoucherDetailsTab {...props()} />)

    expect(screen.getByRole('combobox', { name: 'Currency' })).toBeTruthy()
    expect(
      screen.queryByRole('combobox', { name: 'Reporting currency' }),
    ).toBeNull()
  })

  it('leaves the number empty when the document stated none', () => {
    render(<VoucherDetailsTab {...props()} />)

    expect(
      screen.getByLabelText<HTMLInputElement>(/invoice number/i).value,
    ).toBe('')
  })

  it('shows the ERP’s own number as evidence, not as a field', () => {
    render(<VoucherDetailsTab {...props()} />)

    expect(screen.getByText(/ERP reference/i)).toBeTruthy()
    expect(screen.getByText('INV-2026-0412')).toBeTruthy()
    expect(screen.queryByLabelText(/ERP reference/i)).toBeNull()
  })

  it('surfaces a save failure rather than swallowing it', async () => {
    const onUpdateHeader = vi.fn().mockRejectedValue(new Error('boom'))
    render(<VoucherDetailsTab {...props({ onUpdateHeader })} />)

    fireEvent.change(screen.getByLabelText(/invoice number/i), {
      target: { value: 'INV-BAD' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByText(/boom/i)).toBeTruthy()
  })

  it('reports the header dirty while an edit is uncommitted, and clean again once saved', async () => {
    const onHeaderDirtyChange = vi.fn()
    render(<VoucherDetailsTab {...props({ onHeaderDirtyChange })} />)
    expect(onHeaderDirtyChange).toHaveBeenLastCalledWith(false)

    fireEvent.change(screen.getByLabelText(/invoice number/i), {
      target: { value: 'INV-DRAFT' },
    })
    expect(onHeaderDirtyChange).toHaveBeenLastCalledWith(true)

    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(onHeaderDirtyChange).toHaveBeenLastCalledWith(false),
    )
  })

  it('tracks the invoice prop rather than only its value at mount', () => {
    const invoiceA = invoice({ id: 'inv-a', document_invoice_number: 'INV-A' })
    const invoiceB = invoice({ id: 'inv-b', document_invoice_number: 'INV-B' })

    const { rerender } = render(
      <VoucherDetailsTab {...props({ invoice: invoiceA })} />,
    )
    expect(
      screen.getByLabelText<HTMLInputElement>(/invoice number/i).value,
    ).toBe('INV-A')

    rerender(<VoucherDetailsTab {...props({ invoice: invoiceB })} />)
    expect(
      screen.getByLabelText<HTMLInputElement>(/invoice number/i).value,
    ).toBe('INV-B')
  })
})
