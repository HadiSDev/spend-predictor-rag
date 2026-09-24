import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { VoucherPostingsTab } from './voucher-postings-tab'
import type { ErpEntryRead } from '#/lib/types'

/** One posting. Converted at rate 1 by default — the ordinary, same-currency case. */
function entry(overrides: Partial<ErpEntryRead> = {}): ErpEntryRead {
  const row = {
    id: 'e1',
    company_id: 'c1',
    erp_account_id: 'a1',
    source_invoice_id: 'inv1',
    voucher_id: 'V-1042',
    entry_type: 'purchase_invoice',
    accounting_date: '2026-07-02',
    description: 'Acme SaaS July',
    debit_amount: '1200.00',
    credit_amount: null,
    currency: 'DKK',
    erp_entry_id: 'ERP-1',
    status: 'pending',
    error_message: null as string | null,
    created_at: '2026-07-02T09:00:00Z',
    erp_account_code: '6200',
    erp_account_name: 'Software',
    erp_account_type: 'expense',
    vendor_id: 'v1',
    vendor_name: 'Contoso ApS',
    source_invoice_line_id: null as string | null,
    spend_category_level_1: null as string | null,
    spend_category_level_2: null as string | null,
    spend_category_level_3: null as string | null,
    base_currency: 'DKK' as string | null,
    base_debit_amount: null,
    base_credit_amount: null,
    fx_rate: '1' as string | null,
    fx_rate_date: '2026-07-02' as string | null,
    ...overrides,
  }
  return {
    ...row,
    base_debit_amount:
      overrides.base_debit_amount ?? (row.base_currency ? row.debit_amount : null),
    base_credit_amount:
      overrides.base_credit_amount ?? (row.base_currency ? row.credit_amount : null),
  }
}

const PAYABLE: ErpEntryRead = entry({
  id: 'e3',
  erp_account_code: '8100',
  erp_account_name: 'Payables',
  erp_account_type: 'liability',
  debit_amount: '0.00',
  credit_amount: '1200.00',
})

describe('VoucherPostingsTab', () => {
  it('shows one collapsible block per posting, closed by default', () => {
    render(<VoucherPostingsTab entries={[entry(), PAYABLE]} />)

    const button = screen.getByRole('button', { name: /6200/ })
    expect(button.getAttribute('aria-expanded')).toBe('false')
    // The header carries the account and the signed amount…
    expect(within(button).getByText('Software')).toBeTruthy()
    expect(within(button).getByText('DKK 1,200.00')).toBeTruthy()
    // …but the rest of the fields are not rendered until it opens.
    expect(screen.queryByText('Acme SaaS July')).toBeNull()
  })

  it('reveals the full field list on expand and flips aria-expanded', () => {
    render(<VoucherPostingsTab entries={[entry()]} />)

    const button = screen.getByRole('button', { name: /6200/ })
    fireEvent.click(button)

    expect(button.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('Acme SaaS July')).toBeTruthy()
    expect(screen.getByText('purchase_invoice')).toBeTruthy()
    expect(screen.getByText('2026-07-02')).toBeTruthy()
    expect(screen.getByText('Contoso ApS')).toBeTruthy()
    expect(screen.getByText('inv1')).toBeTruthy()
    expect(screen.getByText('ERP-1')).toBeTruthy()
    expect(screen.getByText('pending')).toBeTruthy()
  })

  it('collapses again on a second click', () => {
    render(<VoucherPostingsTab entries={[entry()]} />)
    const button = screen.getByRole('button', { name: /6200/ })

    fireEvent.click(button)
    expect(screen.getByText('Acme SaaS July')).toBeTruthy()

    fireEvent.click(button)
    expect(button.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('Acme SaaS July')).toBeNull()
  })

  it('explains a converted figure with labelled fields, not a tooltip only', () => {
    const converted = entry({
      id: 'm1',
      currency: 'EUR',
      debit_amount: '100.00',
      base_debit_amount: '746.00',
      fx_rate: '7.46',
      fx_rate_date: '2026-02-02',
    })
    render(<VoucherPostingsTab entries={[converted]} />)
    fireEvent.click(screen.getByRole('button', { name: /6200/ }))

    expect(screen.getByText('Debit (DKK)')).toBeTruthy()
    expect(screen.getByText('DKK 746.00')).toBeTruthy()
    expect(screen.getByText('Exchange rate')).toBeTruthy()
    expect(screen.getByText('7.46')).toBeTruthy()
    expect(screen.getByText('Rate date')).toBeTruthy()
    // The posted figure stays visible as the evidence (once in the header,
    // once in the Debit field).
    expect(screen.getAllByText('€100.00').length).toBe(2)
  })

  it('says plainly when a posting was not converted, with no rate to show', () => {
    const unconverted = entry({
      id: 'g1',
      currency: 'GBP',
      debit_amount: '500.00',
      base_currency: null,
      base_debit_amount: null,
      fx_rate: null,
      fx_rate_date: null,
    })
    render(<VoucherPostingsTab entries={[unconverted]} />)
    fireEvent.click(screen.getByRole('button', { name: /6200/ }))

    expect(screen.getByText(/Not converted/)).toBeTruthy()
    expect(screen.queryByText('Exchange rate')).toBeNull()
  })

  it('adds no conversion rows for a posting already in the company’s currency', () => {
    render(<VoucherPostingsTab entries={[entry()]} />)
    fireEvent.click(screen.getByRole('button', { name: /6200/ }))

    expect(screen.queryByText('Exchange rate')).toBeNull()
    expect(screen.queryByText('Rate date')).toBeNull()
  })

  it('renders no input elements — evidence, never an editable or disabled control', () => {
    render(<VoucherPostingsTab entries={[entry()]} />)
    fireEvent.click(screen.getByRole('button', { name: /6200/ }))

    expect(document.querySelectorAll('input, textarea').length).toBe(0)
    expect(document.querySelectorAll('button:disabled').length).toBe(0)
  })

  it('badges a failed posting and shows its error message', () => {
    const failed = entry({
      id: 'f1',
      status: 'failed',
      error_message: 'ERP rejected the posting',
    })
    render(<VoucherPostingsTab entries={[failed]} />)
    expect(screen.getAllByText('failed').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /6200/ }))
    expect(screen.getByText('ERP rejected the posting')).toBeTruthy()
  })

  it('renders a signed amount for a credit posting, never a raw 0.00', () => {
    render(<VoucherPostingsTab entries={[PAYABLE]} />)
    // debit 0.00 - credit 1200.00 = -1200.00, formatted with a minus sign.
    expect(screen.getByText(/-.*1,200\.00/)).toBeTruthy()
  })

  it('shows a message rather than an empty list when the voucher has no postings', () => {
    render(<VoucherPostingsTab entries={[]} />)
    expect(screen.getByText(/no postings/i)).toBeTruthy()
  })
})
