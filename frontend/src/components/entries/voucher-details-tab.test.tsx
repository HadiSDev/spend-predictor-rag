import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { VoucherDetailsTab } from './voucher-details-tab'
import type { VoucherDetailsTabProps } from './voucher-details-tab'
import type { InvoiceDetailRead, InvoiceLineRead } from '#/lib/types'

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
    verified_fields: [],
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
    lines: [line()],
    lines_reconciled: true,
    reconciliation_delta: null,
    ...overrides,
  }
}

const erpInvoice = invoice()

/** The props every render needs, so a test states only what it is about. */
function props(overrides: Partial<VoucherDetailsTabProps> = {}): VoucherDetailsTabProps {
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
  it('lets a manager correct an ERP-sourced header', () => {
    // Provenance used to decide this, and gated on a value no production
    // invoice ever carried — so the editor existed and no customer could reach
    // it. What decides it now is the reader's role.
    render(<VoucherDetailsTab {...props()} />)
    expect(screen.getByLabelText(/invoice number/i)).toBeTruthy()
  })

  it('shows a read-only role evidence text, never a disabled input', () => {
    // A disabled input claims a permission that will never be granted.
    render(<VoucherDetailsTab {...props({ canManage: false })} />)
    expect(screen.getByText('INV-2026-0412')).toBeTruthy()
    expect(screen.queryByLabelText(/invoice number/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /^save$/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /verify header/i })).toBeNull()
  })

  it('carries the ERP provenance as text, not colour alone', () => {
    // Still shown: it says how much to trust a value, which is a different
    // question from whether the value may be corrected.
    render(<VoucherDetailsTab {...props()} />)
    expect(screen.getByText(/erp posting/i)).toBeTruthy()
  })

  it('saves only the header fields that changed', async () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab {...props({ onUpdateHeader })} />)

    fireEvent.change(screen.getByLabelText(/invoice number/i), { target: { value: 'INV-CORRECTED' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(onUpdateHeader).toHaveBeenCalledWith(erpInvoice.id, {
        invoice_number: 'INV-CORRECTED',
      }),
    )
  })

  it('sends a supplier correction without touching the vendor link', async () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab {...props({ onUpdateHeader })} />)

    fireEvent.change(screen.getByLabelText(/vat number/i), { target: { value: 'DE123456789' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(onUpdateHeader).toHaveBeenCalledWith(erpInvoice.id, {
        supplier_vat_number: 'DE123456789',
      }),
    )
  })

  it('says a supplier correction applies to this invoice only', () => {
    // The catalog is shared across organizations; a reviewer who thinks they
    // are fixing it everywhere would be wrong.
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
    expect(screen.getByRole('button', { name: /^save$/i })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: /^cancel$/i })).toHaveProperty('disabled', true)
  })

  it('offers verify even with nothing edited', () => {
    // Accepting the parsed values unchanged is itself the signal — "I read
    // these and they are right" — and it is the one a correction cannot make.
    const onVerifyHeader = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab {...props({ onVerifyHeader })} />)

    const verify = screen.getByRole('button', { name: /verify header/i })
    expect(verify).toHaveProperty('disabled', false)
    fireEvent.click(verify)

    return waitFor(() => expect(onVerifyHeader).toHaveBeenCalledWith(erpInvoice.id, {}))
  })

  it('verifies the pending edit along with the verification', async () => {
    const onVerifyHeader = vi.fn().mockResolvedValue(undefined)
    render(<VoucherDetailsTab {...props({ onVerifyHeader })} />)

    fireEvent.change(screen.getByLabelText(/^tax$/i), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: /save and verify/i }))

    await waitFor(() => expect(onVerifyHeader).toHaveBeenCalledWith(erpInvoice.id, { tax: 25 }))
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
    render(<VoucherDetailsTab {...props({ onUpdateHeader })} />)

    fireEvent.change(screen.getByLabelText(/invoice number/i), { target: { value: 'INV-DRAFT' } })
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }))

    expect(screen.getByLabelText<HTMLInputElement>(/invoice number/i).value).toBe('INV-2026-0412')
    expect(onUpdateHeader).not.toHaveBeenCalled()
  })

  it('surfaces a save failure rather than swallowing it', async () => {
    const onUpdateHeader = vi.fn().mockRejectedValue(new Error('boom'))
    render(<VoucherDetailsTab {...props({ onUpdateHeader })} />)

    fireEvent.change(screen.getByLabelText(/invoice number/i), { target: { value: 'INV-BAD' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByText(/boom/i)).toBeTruthy()
  })

  it('reports the header dirty while an edit is uncommitted, and clean again once saved', async () => {
    const onHeaderDirtyChange = vi.fn()
    render(<VoucherDetailsTab {...props({ onHeaderDirtyChange })} />)
    expect(onHeaderDirtyChange).toHaveBeenLastCalledWith(false)

    fireEvent.change(screen.getByLabelText(/invoice number/i), { target: { value: 'INV-DRAFT' } })
    expect(onHeaderDirtyChange).toHaveBeenLastCalledWith(true)

    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(onHeaderDirtyChange).toHaveBeenLastCalledWith(false))
  })

  it('tracks the invoice prop rather than only its value at mount', () => {
    // A drawer that stays mounted while the selected voucher changes must not
    // leave the header showing the previous invoice's values.
    const invoiceA = invoice({ id: 'inv-a', invoice_number: 'INV-A' })
    const invoiceB = invoice({ id: 'inv-b', invoice_number: 'INV-B' })

    const { rerender } = render(<VoucherDetailsTab {...props({ invoice: invoiceA })} />)
    expect(screen.getByLabelText<HTMLInputElement>(/invoice number/i).value).toBe('INV-A')

    rerender(<VoucherDetailsTab {...props({ invoice: invoiceB })} />)
    expect(screen.getByLabelText<HTMLInputElement>(/invoice number/i).value).toBe('INV-B')
  })
})
