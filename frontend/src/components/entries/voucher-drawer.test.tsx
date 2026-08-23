import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { VoucherDrawer } from './voucher-drawer'
import type { VoucherDrawerProps } from './voucher-drawer'
import type {
  ErpEntryRead,
  InvoiceDetailRead,
  InvoiceLineRead,
  VoucherAuditRead,
  VoucherDetailRead,
} from '#/lib/types'

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

// `InvoiceDocument` fetches its own data (a query client + Clerk auth), which
// is plumbing this drawer never touches — it is presentational and renders
// whatever it is handed. That component's own behaviour is covered by
// invoice-document.test.tsx; here it is stubbed down to its identifying
// props so the drawer's composition (layout, tabs, header) is what's under
// test.
vi.mock('./invoice-document', () => ({
  InvoiceDocument: ({ invoiceId, filename }: { invoiceId: string | null; filename: string | null }) => (
    <div data-testid="invoice-document">
      invoice:{invoiceId ?? 'none'} file:{filename ?? 'none'}
    </div>
  ),
}))

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
    erp_account_type: 'expense' as string | null,
    vendor_id: 'v1',
    vendor_name: 'Contoso ApS' as string | null,
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
    base_debit_amount: overrides.base_debit_amount ?? (row.base_currency ? row.debit_amount : null),
    base_credit_amount: overrides.base_credit_amount ?? (row.base_currency ? row.credit_amount : null),
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

function line(overrides: Partial<InvoiceLineRead> = {}): InvoiceLineRead {
  return {
    id: 'l1',
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
    fx_rate_date: '2026-07-02',
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
    rationale: 'Matched on "chair".',
    spend_category_id: 'cat-chairs',
    level_4: null,
    category_stale: false,
    verified_fields: [],
    ...overrides,
  }
}

function invoice(overrides: Partial<InvoiceDetailRead> = {}): InvoiceDetailRead {
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
    file_id: 'file-1',
    file_name: 'acme-invoice.pdf',
    has_document: true,
    doc_status: 'processed',
    doc_error: null,
    doc_processed_at: '2026-07-02T10:00:00Z',
    lines: [line()],
    lines_reconciled: true,
    reconciliation_delta: null,
    ...overrides,
  }
}

/** A purchase voucher with its PDF attached — the wide-layout case.
 *
 * `amount`/`currency` are deliberately set to a figure that does *not* match
 * what summing `entries` client-side would produce (1,200.00, the sum of the
 * as-posted DKK postings below). The server computes the total — including
 * currency conversion for a voucher posted in a non-base currency — and the
 * drawer must render exactly that figure, never its own recomputation from
 * the postings. If the header ever starts reading the postings instead of
 * `detail.amount`, the assertions below fail loudly rather than by
 * coincidentally landing on the same number. */
const withInvoice: VoucherDetailRead = {
  voucher_id: 'V-1042',
  company_id: 'c1',
  accounting_date: '2026-07-02',
  currency: 'DKK',
  amount: '746.00',
  entry_count: 2,
  entries: [entry(), PAYABLE],
  invoice: invoice(),
  document: { file_id: 'file-1', filename: 'acme-invoice.pdf' },
}

/** A journal entry — no invoice, no document. The common case. */
const journalOnly: VoucherDetailRead = {
  voucher_id: 'V-9001',
  company_id: 'c1',
  accounting_date: '2026-07-03',
  currency: 'DKK',
  amount: '50.00',
  entry_count: 1,
  entries: [
    entry({
      id: 'j1',
      voucher_id: 'V-9001',
      entry_type: 'journal_entry',
      source_invoice_id: null,
      source_invoice_line_id: null,
      erp_account_type: 'expense',
      debit_amount: '50.00',
      credit_amount: null,
    }),
  ],
  invoice: null,
  document: null,
}

function auditRow(overrides: Partial<VoucherAuditRead> = {}): VoucherAuditRead {
  return {
    id: 'a1',
    entity_type: 'invoice_line',
    entity_id: 'l1',
    entity_label: 'Office chairs',
    action: 'verify',
    actor: 'user_123',
    changes: [{ field: 'level_2', old: 'Office supplies', new: 'Furniture' }],
    created_at: '2026-07-02T09:05:00Z',
    ...overrides,
  }
}

const AUDIT: Array<VoucherAuditRead> = [
  auditRow({ id: 'a2', action: 'verify', entity_label: 'Office chairs (corrected)', created_at: '2026-07-02T10:00:00Z' }),
  auditRow({ id: 'a1', action: 'ai_categorize', actor: 'system', created_at: '2026-07-02T09:00:00Z' }),
]

function props(overrides: Partial<VoucherDrawerProps> = {}): VoucherDrawerProps {
  return {
    detail: withInvoice,
    loading: false,
    auditRows: [],
    auditLoading: false,
    tab: 'details',
    open: true,
    onTabChange: vi.fn(),
    onOpenChange: vi.fn(),
    onVerifyLine: vi.fn().mockResolvedValue(undefined),
    spendTreeNodes: TREE_NODES,
    onReprocess: vi.fn().mockResolvedValue(undefined),
    canManage: true,
    vendors: [],
    onUpdateHeader: vi.fn().mockResolvedValue(undefined),
    onVerifyHeader: vi.fn().mockResolvedValue(undefined),
    onUpdateLine: vi.fn().mockResolvedValue(undefined),
    onCreateLine: vi.fn().mockResolvedValue(undefined),
    onDeleteLine: vi.fn().mockResolvedValue(undefined),
    hasUnsavedChanges: false,
    ...overrides,
  }
}

describe('VoucherDrawer — layout', () => {
  it('shows the document beside the detail when an invoice is attached', () => {
    render(<VoucherDrawer {...props({ detail: withInvoice })}
        spendTreeNodes={TREE_NODES} />)
    expect(screen.getByLabelText('Voucher detail').className).toContain('max-w-[1100px]')
    expect(screen.getByRole('tab', { name: /details/i })).toBeTruthy()
    expect(screen.getByTestId('invoice-document')).toBeTruthy()
  })

  it('collapses to postings when the voucher has no invoice', () => {
    render(<VoucherDrawer {...props({ detail: journalOnly, tab: 'postings' })}
        spendTreeNodes={TREE_NODES} />)
    expect(screen.getByLabelText('Voucher detail').className).not.toContain('max-w-[1100px]')
    expect(screen.queryByRole('tab', { name: /details/i })).toBeNull()
    expect(screen.queryByRole('tab', { name: /postings/i })).toBeTruthy()
    // No PDF column and no empty frame for one.
    expect(screen.queryByTestId('invoice-document')).toBeNull()
  })

  it('falls back off the details tab when the voucher has no invoice to show one', () => {
    // The controlled `tab` prop still says "details" — e.g. a stale URL from
    // a voucher that used to have an invoice. Falling back to Postings beats
    // rendering nothing.
    render(<VoucherDrawer {...props({ detail: journalOnly, tab: 'details' })}
        spendTreeNodes={TREE_NODES} />)
    expect(screen.getByRole('tabpanel', { name: /postings/i })).toBeTruthy()
  })

  it('corrects the URL to match the tab it fell back to, rather than leaving the two disagreeing', () => {
    const onTabChange = vi.fn()
    render(<VoucherDrawer {...props({ detail: journalOnly, tab: 'details', onTabChange })}
        spendTreeNodes={TREE_NODES} />)
    expect(onTabChange).toHaveBeenCalledWith('postings')
  })

  it('leaves the URL alone once it already names a tab this voucher has', () => {
    const onTabChange = vi.fn()
    render(<VoucherDrawer {...props({ detail: withInvoice, tab: 'details', onTabChange })}
        spendTreeNodes={TREE_NODES} />)
    expect(onTabChange).not.toHaveBeenCalled()
  })

  it('does not correct the URL while the detail is still loading', () => {
    // `hasInvoice` defaults to false with no detail yet — correcting now would
    // "fall back" a tab that turns out to be valid the moment it loads.
    const onTabChange = vi.fn()
    render(<VoucherDrawer {...props({ detail: undefined, loading: true, tab: 'details', onTabChange })}
        spendTreeNodes={TREE_NODES} />)
    expect(onTabChange).not.toHaveBeenCalled()
  })

  it('shows a loading skeleton rather than a blank drawer while the detail loads', () => {
    render(<VoucherDrawer {...props({ detail: undefined, loading: true })}
        spendTreeNodes={TREE_NODES} />)
    // The drawer's content is portaled to `document.body`, not the render
    // container, so the skeleton is looked up from there.
    expect(document.body.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
    expect(screen.queryByRole('tab', { name: /postings/i })).toBeNull()
  })
})

describe('VoucherDrawer — header', () => {
  it('shows voucher id, supplier, date, posting count and total', () => {
    render(<VoucherDrawer {...props({ detail: withInvoice })}
        spendTreeNodes={TREE_NODES} />)
    const header = within(screen.getByText('V-1042').closest('div')!)
    expect(header.getByText('V-1042')).toBeTruthy()
    expect(header.getByText(/Contoso ApS/)).toBeTruthy()
    expect(header.getByText(/2026-07-02/)).toBeTruthy()
    expect(header.getByText(/2 postings/)).toBeTruthy()
    expect(header.getByText(/DKK 746\.00/)).toBeTruthy()
  })

  it('renders the server-computed total, never a client-side recomputation from the postings', () => {
    // Regression: the drawer used to sum `entries` itself, in their as-posted
    // currency. For a voucher posted in a non-base currency that showed a
    // different figure, in a different currency, than the same voucher's row
    // in the table (which base-converts). `withInvoice.amount`/`currency`
    // deliberately disagree with what the as-posted DKK postings sum to
    // (1,200.00) — if the header ever shows that instead of the payload's
    // 746.00, the client math is back.
    render(<VoucherDrawer {...props({ detail: withInvoice })}
        spendTreeNodes={TREE_NODES} />)
    const header = within(screen.getByText('V-1042').closest('div')!)

    expect(header.getByText(/DKK 746\.00/)).toBeTruthy()
    expect(header.queryByText(/1,200\.00/)).toBeNull()
  })

  it('labels a voucher with no id as "No voucher"', () => {
    render(<VoucherDrawer {...props({ detail: { ...journalOnly, voucher_id: null }, tab: 'postings' })}
        spendTreeNodes={TREE_NODES} />)
    expect(screen.getByText('No voucher')).toBeTruthy()
  })
})

describe('VoucherDrawer — tabs', () => {
  it('renders the audit feed newest first with what changed', () => {
    render(<VoucherDrawer {...props({ detail: withInvoice, tab: 'activity', auditRows: AUDIT })}
        spendTreeNodes={TREE_NODES} />)
    const items = screen.getAllByRole('listitem')
    expect(within(items[0]).getByText(/corrected/i)).toBeTruthy()
  })

  it('reports a tab click back to the owner rather than switching itself', () => {
    const onTabChange = vi.fn()
    render(<VoucherDrawer {...props({ detail: withInvoice, tab: 'details', onTabChange })}
        spendTreeNodes={TREE_NODES} />)
    fireEvent.click(screen.getByRole('tab', { name: /postings/i }))
    expect(onTabChange).toHaveBeenCalledWith('postings')
  })

  it('renders the postings passed on the detail', () => {
    render(<VoucherDrawer {...props({ detail: withInvoice, tab: 'postings' })}
        spendTreeNodes={TREE_NODES} />)
    expect(screen.getByRole('button', { name: /6200/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /8100/ })).toBeTruthy()
  })

  it('passes verify-line submissions through to the owner', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    // The line editors live on the Lines tab: the line is the unit this
    // product works in, not a footnote to a header nobody edits.
    render(<VoucherDrawer {...props({ detail: withInvoice, tab: 'lines', onVerifyLine })}
        spendTreeNodes={TREE_NODES} />)
    fireEvent.click(screen.getByRole('button', { name: /accept/i }))
    expect(onVerifyLine).toHaveBeenCalledWith('l1', {})
  })

  it('passes a header save through to the owner, for a correctable invoice', async () => {
    const onUpdateHeader = vi.fn().mockResolvedValue(undefined)
    const parsed = { ...withInvoice, invoice: invoice({ source: 'pdf_extraction' }) }
    render(<VoucherDrawer {...props({ detail: parsed, tab: 'details', onUpdateHeader })}
        spendTreeNodes={TREE_NODES} />)

    fireEvent.change(screen.getByLabelText(/invoice number/i), { target: { value: 'INV-9' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(onUpdateHeader).toHaveBeenCalledWith('inv1', { invoice_number: 'INV-9' })
  })
})

describe('VoucherDrawer — dismissal', () => {
  it('closes immediately when there are no unsaved edits', async () => {
    const onOpenChange = vi.fn()
    render(<VoucherDrawer {...props({ onOpenChange, hasUnsavedChanges: false })}
        spendTreeNodes={TREE_NODES} />)
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  })

  it('asks for confirmation before dismissing with unsaved edits, rather than closing outright', async () => {
    const onOpenChange = vi.fn()
    render(<VoucherDrawer {...props({ onOpenChange, hasUnsavedChanges: true })}
        spendTreeNodes={TREE_NODES} />)
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })

    expect(await screen.findByRole('heading', { name: /discard unsaved changes/i })).toBeTruthy()
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  it('discards and closes once the user confirms', async () => {
    const onOpenChange = vi.fn()
    render(<VoucherDrawer {...props({ onOpenChange, hasUnsavedChanges: true })}
        spendTreeNodes={TREE_NODES} />)
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })

    fireEvent.click(await screen.findByRole('button', { name: /discard changes/i }))
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  })

  it('keeps the drawer open when the user chooses to keep editing', async () => {
    const onOpenChange = vi.fn()
    render(<VoucherDrawer {...props({ onOpenChange, hasUnsavedChanges: true })}
        spendTreeNodes={TREE_NODES} />)
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })

    fireEvent.click(await screen.findByRole('button', { name: /keep editing/i }))
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Voucher detail')).toBeTruthy()
  })
})

describe('VoucherDrawer — accessibility', () => {
  it('names the drawer for assistive tech', () => {
    render(<VoucherDrawer {...props()}
        spendTreeNodes={TREE_NODES} />)
    expect(screen.getByLabelText('Voucher detail')).toBeTruthy()
  })

  it('gives the mobile document toggle a real accessible name', () => {
    render(<VoucherDrawer {...props({ detail: withInvoice, tab: 'postings' })}
        spendTreeNodes={TREE_NODES} />)
    expect(screen.getByRole('button', { name: /view document/i })).toBeTruthy()
  })
})
