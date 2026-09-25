import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DocumentProcessing } from './document-processing'
import type { DocStatus, InvoiceDetailRead } from '#/lib/api/types'

function invoice(
  overrides: Partial<InvoiceDetailRead> = {},
): InvoiceDetailRead {
  return {
    id: 'inv1',
    company_id: 'c1',
    vendor_id: 'v1',
    invoice_number: 'INV-2026-0412',
    document_invoice_number: null,
    invoice_date: '2026-07-02',
    currency: 'DKK',
    total: '1200.00',
    tax: '300.00',
    base_currency: 'DKK',
    base_total: '1200.00',
    base_tax: '300.00',
    fx_rate: '1',
    fx_rate_date: '2026-07-02',
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
    file_id: 'f1',
    file_name: 'invoice.pdf',
    has_document: true,
    doc_status: 'processed',
    doc_error: null,
    doc_processed_at: '2026-07-02T10:00:00Z',
    document_total: null,
    document_tax: null,
    totals_agree: null,
    lines: [],
    lines_reconciled: true,
    reconciliation_delta: null,
    ...overrides,
  }
}

function setup(
  overrides: Partial<InvoiceDetailRead> = {},
  canRetrigger = true,
) {
  const onReprocess = vi.fn().mockResolvedValue(undefined)
  render(
    <DocumentProcessing
      invoice={invoice(overrides)}
      canRetrigger={canRetrigger}
      onReprocess={onReprocess}
    />,
  )
  return onReprocess
}

const action = () =>
  screen.queryByRole('button', { name: /process document again/i })

describe('DocumentProcessing', () => {
  it('states a failure and its reason, so the user is not asked to retry blind', () => {
    setup({
      doc_status: 'failed',
      doc_error: 'inv-1.jpg: no extractor for media type “image/jpeg”',
    })

    expect(screen.getByText('Failed')).toBeTruthy()
    expect(screen.getByText(/image\/jpeg/)).toBeTruthy()
    expect(action()).toBeTruthy()
  })

  it('reports a retrigger to the owner', async () => {
    const onReprocess = setup({ doc_status: 'failed', doc_error: 'nope' })

    fireEvent.click(action()!)

    await waitFor(() => expect(onReprocess).toHaveBeenCalledWith('inv1'))
  })

  it('offers the action on a processed invoice, so a bad extraction can be redone', () => {
    setup({ doc_status: 'processed' })
    expect(action()).toBeTruthy()
  })

  it('offers no action while a run is in flight, which the API would refuse', () => {
    setup({ doc_status: 'processing' })
    expect(action()).toBeNull()
  })

  it('offers no action where there is no document to process', () => {
    setup({ doc_status: 'not_applicable', has_document: false, file_id: null })
    expect(action()).toBeNull()
  })

  it('offers no action to a user without the role the endpoint requires', () => {
    setup({ doc_status: 'failed', doc_error: 'nope' }, false)

    expect(screen.getByText('Failed')).toBeTruthy()
    expect(screen.getByText('nope')).toBeTruthy()
    expect(action()).toBeNull()
  })

  it('states a missing document plainly, not as a failure', () => {
    setup({ doc_status: 'not_applicable', has_document: false, file_id: null })

    expect(screen.getByText('No document')).toBeTruthy()
    expect(screen.getByText(/stand in for its postings/)).toBeTruthy()
  })

  it('says the work is queued, so a retrigger does not look lost', () => {
    setup({ doc_status: 'pending' })
    expect(screen.getByText('Queued')).toBeTruthy()
  })

  it.each<DocStatus>([
    'not_applicable',
    'pending',
    'processing',
    'processed',
    'failed',
  ])('has something to say about %s', (doc_status) => {
    setup({ doc_status })
    expect(screen.getByRole('heading', { name: 'Document' })).toBeTruthy()
  })
})
