import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DocumentTotal } from './document-total'
import type { InvoiceDetailRead } from '#/lib/api/types'

function invoice(
  overrides: Partial<InvoiceDetailRead> = {},
): InvoiceDetailRead {
  return {
    id: 'inv1',
    company_id: 'c1',
    vendor_id: 'v1',
    invoice_number: 'INV-1',
    document_invoice_number: null,
    invoice_date: '2026-04-12',
    currency: 'DKK',
    total: '90.00',
    tax: '0.00',
    base_currency: 'DKK',
    base_total: '90.00',
    base_tax: '0.00',
    fx_rate: '1',
    fx_rate_date: '2026-04-12',
    supplier_name: 'Aquatuning GmbH',
    supplier_country_code: 'DE',
    supplier_vat_number: null,
    supplier_overrides: [],
    status: 'categorized',
    source: 'erp',
    verified_fields: [],
    verified_at: null,
    verified_by: null,
    error_message: null,
    file_id: 'f1',
    file_name: 'inv.pdf',
    has_document: true,
    doc_status: 'processed',
    doc_error: null,
    doc_processed_at: '2026-04-13T09:00:00Z',
    document_total: null,
    document_tax: null,
    totals_agree: null,
    lines: [],
    lines_reconciled: true,
    reconciliation_delta: null,
    ...overrides,
  }
}

describe('DocumentTotal', () => {
  it('shows both figures, each labelled by source, when they disagree', () => {
    render(
      <DocumentTotal
        invoice={invoice({
          document_total: '104.85',
          document_tax: '20.97',
          totals_agree: false,
        })}
      />,
    )

    const note = screen.getByRole('note')
    expect(note.textContent).toContain('document')
    expect(note.textContent).toContain('104.85')
    expect(note.textContent).toContain('ledger')
    expect(note.textContent).toContain('90.00')
  })

  it('shows nothing when the two totals agree', () => {
    render(
      <DocumentTotal
        invoice={invoice({ document_total: '90.00', totals_agree: true })}
      />,
    )

    expect(screen.queryByRole('note')).toBeNull()
  })

  it('shows nothing, and implies no comparison, when the document stated no total', () => {
    render(<DocumentTotal invoice={invoice()} />)

    expect(screen.queryByRole('note')).toBeNull()
  })

  it('omits the VAT clause when the document stated no VAT', () => {
    render(
      <DocumentTotal
        invoice={invoice({
          document_total: '104.85',
          document_tax: null,
          totals_agree: false,
        })}
      />,
    )

    expect(screen.getByRole('note').textContent).not.toContain('VAT')
  })
})
