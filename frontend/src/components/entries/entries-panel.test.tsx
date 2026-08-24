import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { EntriesPanel } from './entries-panel'
import type { EntriesPanelProps } from './entries-panel'
import type {
  CompanyRead,
  ErpEntryRead,
  InvoiceDetailRead,
  InvoiceLineRead,
  VendorRead,
  VoucherDetailRead,
  VoucherGroupRead,
} from '#/lib/types'

/** The company's spend tree, matching the line fixture's own path. */
const TREE_NODES = [
  { id: 'n1', spend_tree_id: 'tree1', parent_id: null, depth: 1, name: 'Indirect',
    code: null, sort_order: 0, description: null,
    level_1: 'Indirect', level_2: null, level_3: null, level_4: null },
  { id: 'n2', spend_tree_id: 'tree1', parent_id: 'n1', depth: 2, name: 'Technology',
    code: null, sort_order: 0, description: null,
    level_1: 'Indirect', level_2: 'Technology', level_3: null, level_4: null },
  { id: 'cat-software', spend_tree_id: 'tree1', parent_id: 'n2', depth: 3,
    name: 'Software Subscriptions', code: '6200', sort_order: 0, description: null,
    level_1: 'Indirect', level_2: 'Technology', level_3: 'Software Subscriptions',
    level_4: null },
]

// `VoucherDrawer` fetches nothing itself — it is presentational, same as this
// panel. `InvoiceDocument`, nested inside it, does fetch (needs a Clerk
// bearer token via `useApi`), which this file has no `ClerkProvider` for — so
// it is stubbed down to its identifying props, same as `voucher-drawer.test.tsx`.
vi.mock('./invoice-document', () => ({
  InvoiceDocument: ({ invoiceId, filename }: { invoiceId: string | null; filename: string | null }) => (
    <div data-testid="invoice-document">
      invoice:{invoiceId ?? 'none'} file:{filename ?? 'none'}
    </div>
  ),
}))

const ACME: CompanyRead = {
  id: 'c1',
  name: 'Acme A/S',
  country_code: 'DK',
  vat_number: 'DK12345678',
  base_currency: 'DKK',
  is_active: true,
  deactivated_at: null,
  spend_tree_id: 'tree1',
  spend_tree_name: 'Default spend tree',
}

const CONTOSO: VendorRead = {
  id: 'v1',
  name: 'Contoso ApS',
  country_code: 'DK',
  vat_number: 'DK99999999',
  description: null,
}

/**
 * A posting. DKK for a DKK-reporting company, so unless a test says otherwise it
 * arrives converted at rate 1 — the ordinary case. The base amounts are derived
 * *after* the overrides, so a test that changes an amount does not leave the
 * converted figure quietly disagreeing with the posted one.
 */
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
    error_message: null,
    created_at: '2026-07-02T09:00:00Z',
    erp_account_code: '6200',
    erp_account_name: 'Software',
    erp_account_type: 'expense',
    vendor_id: 'v1',
    vendor_name: 'Contoso ApS',
    // Uncategorized by default: no line, no category — what a posting looks
    // like before the AI has run, and what most postings look like always.
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

/**
 * One invoice line. `document_ai` by default — the ordinary case once the
 * document has been read, and the one that carries no provenance mark.
 */
function line(overrides: Partial<InvoiceLineRead> = {}): InvoiceLineRead {
  return {
    id: 'l1',
    invoice_id: 'inv1',
    company_id: 'c1',
    item_name: null,
    description: 'Figma Organization, 12 seats',
    quantity: '12.0000',
    unit: 'pcs',
    unit_price: '100.0000',
    amount: '1200.00',
    native_account_code: '6200',
    origin: 'document_ai',
    sequence: 0,
    currency: 'DKK',
    base_currency: 'DKK',
    base_amount: '1200.00',
    fx_rate: '1',
    fx_rate_date: '2026-07-02',
    status: 'ai_categorized',
    level_1: 'Indirect',
    level_2: 'Technology',
    level_3: 'Software Subscriptions',
    account_code: '6200',
    account_name: 'Software',
    confidence: '0.910',
    rationale: 'matched',
    // A categorized line points at the node it was categorized to; null with
    // levels set is the stale shape, asserted on explicitly elsewhere.
    spend_category_id: 'cat-software',
    level_4: null,
    category_stale: false,
    needs_review: false,
    verified_fields: [],
    ...overrides,
  }
}

/** A three-posting voucher, the normal case. */
const VOUCHER: VoucherGroupRead = {
  voucher_id: 'V-1042',
  company_id: 'c1',
  accounting_date: '2026-07-02',
  entry_types: ['purchase_invoice'],
  entry_count: 3,
  amount: '1200.00',       // net spend: the expense posting only
  debit_total: '1500.00',
  credit_total: '1500.00',
  currency: 'DKK',
  unconverted_count: 0,
  vendor_id: 'v1',
  vendor_name: 'Contoso ApS',
  lines: [line()],
  doc_status: 'processed',
  doc_error: null,
  invoice_number: 'INV-2026-0412',
  document_invoice_number: 'INV-2026-0412',
  entries: [
    entry({ id: 'e1', erp_account_code: '6200', erp_account_name: 'Software' }),
    entry({ id: 'e2', erp_account_code: '2610', erp_account_name: 'Input VAT',
            erp_account_type: 'liability', debit_amount: '300.00' }),
    entry({
      id: 'e3',
      erp_account_code: '8100',
      erp_account_name: 'Payables',
      erp_account_type: 'liability',
      // The connector sends 0.00, not null, for the unused side.
      debit_amount: '0.00',
      credit_amount: '1500.00',
    }),
  ],
}

/** Spend split across two expense accounts, plus the payable that balances it. */
const SPLIT: VoucherGroupRead = {
  ...VOUCHER,
  voucher_id: 'V-SPLIT',
  amount: '900.00',
  entry_count: 3,
  lines: [
    line({ id: 'sl1', description: 'Figma seats', amount: '500.00',
           base_amount: '500.00', sequence: 0 }),
    line({ id: 'sl2', description: 'Flights to Berlin', amount: '400.00',
           base_amount: '400.00', sequence: 1,
           level_2: 'Travel', level_3: 'Air Travel' }),
  ],
  entries: [
    entry({ id: 's1', voucher_id: 'V-SPLIT', erp_account_code: '6200',
            erp_account_name: 'Software', erp_account_type: 'expense',
            debit_amount: '500.00' }),
    entry({ id: 's2', voucher_id: 'V-SPLIT', erp_account_code: '6400',
            erp_account_name: 'Travel', erp_account_type: 'expense',
            debit_amount: '400.00' }),
    entry({ id: 's3', voucher_id: 'V-SPLIT', erp_account_code: '8100',
            erp_account_name: 'Payables', erp_account_type: 'liability',
            debit_amount: '0.00', credit_amount: '900.00' }),
  ],
}

/** A posting the ERP gave no voucher id — a group of one. */
const LONE: VoucherGroupRead = {
  voucher_id: null,
  company_id: 'c1',
  accounting_date: null,
  entry_types: ['adjustment'],
  entry_count: 1,
  amount: '5.00',
  debit_total: '5.00',
  credit_total: '0',
  currency: 'DKK',
  unconverted_count: 0,
  vendor_id: null,
  vendor_name: null,
  // A journal entry has no invoice behind it, so no lines and no document.
  lines: [],
  doc_status: null,
  doc_error: null,
  invoice_number: null,
  document_invoice_number: null,
  entries: [
    entry({
      id: 'e9',
      voucher_id: null,
      accounting_date: null,
      entry_type: 'adjustment',
      status: 'failed',
      error_message: 'ERP rejected the posting',
      source_invoice_id: null,
      vendor_id: null,
      vendor_name: null,
      debit_amount: '5.00',
    }),
  ],
}

/** One voucher whose postings disagree on currency. */
const MIXED: VoucherGroupRead = {
  ...VOUCHER,
  voucher_id: 'V-MIX',
  currency: null,
  entry_count: 2,
  amount: '30.00',
  lines: [line({ id: 'ml1', description: 'Mixed voucher line', amount: '30.00',
                base_amount: '30.00' })],
  debit_total: '30.00',
  entries: [
    entry({ id: 'm1', voucher_id: 'V-MIX', currency: 'DKK', debit_amount: '10.00' }),
    entry({ id: 'm2', voucher_id: 'V-MIX', currency: 'EUR', debit_amount: '20.00' }),
  ],
}

function invoiceDetail(overrides: Partial<InvoiceDetailRead> = {}): InvoiceDetailRead {
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
    file_id: null,
    file_name: null,
    has_document: false,
    doc_status: 'not_applicable',
    doc_error: null,
    doc_processed_at: null,
    document_total: null,
    document_tax: null,
    totals_agree: null,
    lines: [],
    lines_reconciled: true,
    reconciliation_delta: null,
    ...overrides,
  }
}

/** The voucher detail payload the panel would fetch after `VOUCHER` is opened. */
const DETAIL: VoucherDetailRead = {
  voucher_id: 'V-1042',
  company_id: 'c1',
  accounting_date: '2026-07-02',
  currency: 'DKK',
  amount: '1200.00',
  entry_count: 3,
  entries: VOUCHER.entries,
  invoice: invoiceDetail(),
  document: null,
}

/** Everything a rendered panel needs that no test varies. */
function common() {
  return {
    loading: false,
    error: false,
    filters: {},
    companies: [ACME],
    vendors: [CONTOSO],
    entryTypes: ['purchase_invoice', 'payment'],
    onFiltersChange: vi.fn(),
    onClearFilters: vi.fn(),
    onPageChange: vi.fn(),
    onVendorSearch: vi.fn(),
    voucherDetail: undefined,
    voucherLoading: false,
    auditRows: [],
    auditLoading: false,
    tab: 'details' as const,
    onTabChange: vi.fn(),
    onSelectEntry: vi.fn(),
    onVerifyLine: vi.fn().mockResolvedValue(undefined),
    spendTreeNodes: TREE_NODES,
    onUpdateHeader: vi.fn().mockResolvedValue(undefined),
    onReprocess: vi.fn().mockResolvedValue(undefined),
    canManage: true,
    onVerifyHeader: vi.fn().mockResolvedValue(undefined),
    onUpdateLine: vi.fn().mockResolvedValue(undefined),
    onCreateLine: vi.fn().mockResolvedValue(undefined),
    onDeleteLine: vi.fn().mockResolvedValue(undefined),
  }
}

function setup(overrides: Partial<EntriesPanelProps> = {}) {
  const props: EntriesPanelProps = {
    result: { items: [VOUCHER], page: 1, page_size: 25, total: 1 },
    ...common(),
    ...overrides,
  }
  render(<EntriesPanel {...props} />)
  return props
}

/** Props for a bare `render` — `setup` renders for us, this one does not. */
function setupProps(overrides: Partial<EntriesPanelProps> = {}): EntriesPanelProps {
  return {
    result: { items: [VOUCHER], page: 1, page_size: 25, total: 1 },
    ...common(),
    entryTypes: ['purchase_invoice'],
    ...overrides,
  }
}

describe('EntriesPanel — voucher rows', () => {
  it('shows one row per voucher with its supplier, date, and totals', () => {
    setup()
    expect(screen.getByText('V-1042')).toBeTruthy()
    expect(screen.getByText('Contoso ApS')).toBeTruthy()
    // The postings are not visible until the group is expanded.
    expect(screen.queryByText('Software')).toBeNull()
  })

  it('offers to expand the ordinary purchase, which has three postings', () => {
    // Expense, VAT and the payable. Nothing is filtered out any more, so the
    // usual voucher does expand — the detail was always there.
    setup()
    expect(screen.getByRole('button', { name: /Expand voucher V-1042/ })).toBeTruthy()
  })

  it('reveals the voucher’s lines, not its postings', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))

    expect(await screen.findByText('Figma Organization, 12 seats')).toBeTruthy()
    // A posting is what the bookkeeper wrote; the plumbing belongs on the
    // panel's Postings tab, where it is read as evidence rather than as spend.
    expect(screen.queryByText('Input VAT')).toBeNull()
    expect(screen.queryByText('Payables')).toBeNull()
  })

  it('opens the panel from the row when there is nothing to expand', () => {
    const props = setup({ result: { items: [LONE], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByText('No voucher'))
    // No voucher id to address it by, so it opens by its lone posting's id.
    expect(props.onSelectEntry).toHaveBeenCalledWith({ voucher: undefined, entry: 'e9' })
  })

  it('gives a voucherless posting no expand affordance', () => {
    setup({ result: { items: [LONE], page: 1, page_size: 25, total: 1 } })
    expect(screen.getByText('No voucher')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Expand voucher/ })).toBeNull()
  })

  it('refuses to sum a mixed-currency voucher', () => {
    setup({ result: { items: [MIXED], page: 1, page_size: 25, total: 1 } })
    expect(screen.getByText('Mixed currencies')).toBeTruthy()
    // 30.00 is 10 DKK + 20 EUR; it must never be presented as one figure.
    expect(screen.queryByText(/30\.00/)).toBeNull()
  })

  it('shows one signed figure rather than a debit and a credit column', () => {
    setup()
    // "Total Spend", not "Total": the rows it expands to sum to zero, so the
    // column must not claim to be their total.
    expect(screen.getByRole('columnheader', { name: 'Total Spend' })).toBeTruthy()
    expect(screen.queryByRole('columnheader', { name: 'Total' })).toBeNull()
    expect(screen.queryByRole('columnheader', { name: 'Debit' })).toBeNull()
    expect(screen.queryByRole('columnheader', { name: 'Credit' })).toBeNull()
    // Net spend, not the gross 1,500 that debit_total and credit_total agree on.
    expect(screen.getByText(/1,200\.00/)).toBeTruthy()
    expect(screen.queryByText(/1,500\.00/)).toBeNull()
  })

  it('offers no Type column, which would read the same on every row', () => {
    // Payments are excluded server-side, so what is left is overwhelmingly
    // purchase_invoice. The type stays in the drawer and as a filter.
    setup()
    expect(screen.queryByRole('columnheader', { name: 'Type' })).toBeNull()
  })

  it('labels the lines, whose columns the voucher header does not describe', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Figma Organization, 12 seats')

    // Without these the description reads under Voucher and the amount under
    // Total Spend — headers that name something else.
    expect(screen.getByRole('columnheader', { name: 'Description' })).toBeTruthy()
    expect(screen.getByRole('columnheader', { name: 'Quantity' })).toBeTruthy()
    expect(screen.getByRole('columnheader', { name: 'Spend category' })).toBeTruthy()
    // "Amount", not "Total Spend": the group's figure is the net of the
    // voucher's expense postings, which is a different quantity.
    expect(screen.getByRole('columnheader', { name: 'Amount' })).toBeTruthy()
  })

  it('says where a line stands, which its empty category cannot', async () => {
    const failed: VoucherGroupRead = {
      ...VOUCHER,
      lines: [line({ status: 'ai_failed', level_1: null, level_2: null, level_3: null })],
    }
    setup({ result: { items: [failed], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Figma Organization, 12 seats')

    expect(screen.getByRole('columnheader', { name: 'Status' })).toBeTruthy()
    const row = screen.getByText('Figma Organization, 12 seats').closest('tr')
    expect(row?.textContent).toContain('failed')
  })

  it('distinguishes a failed line from one nobody has categorized yet', async () => {
    // Both render "—" under Spend category. Only one of them is a problem, and
    // before the Status column there was nothing on the row that said which.
    const mixed: VoucherGroupRead = {
      ...VOUCHER,
      lines: [
        line({ id: 'l-failed', description: 'Togbillet', status: 'ai_failed' }),
        line({ id: 'l-pending', description: 'Kamera', status: 'uncategorized' }),
      ],
    }
    setup({ result: { items: [mixed], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Togbillet')

    const status = screen.getByRole('columnheader', { name: 'Status' })
    const index = [...(status.closest('tr')?.children ?? [])].indexOf(status)
    const cell = (description: string) =>
      screen.getByText(description).closest('tr')?.children[index]?.textContent

    expect(cell('Togbillet')).not.toBe(cell('Kamera'))
  })

  it('shows a line’s spend category as its full path', async () => {
    const categorized: VoucherGroupRead = {
      ...VOUCHER,
      lines: [
        line({
          level_1: 'Indirect',
          level_2: 'Legal',
          level_3: 'Professional Services',
        }),
      ],
    }
    setup({ result: { items: [categorized], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Figma Organization, 12 seats')

    const row = screen.getByText('Figma Organization, 12 seats').closest('tr')
    expect(row?.textContent).toContain('Indirect')
    expect(row?.textContent).toContain('Legal')
    expect(row?.textContent).toContain('Professional Services')
  })

  it('leaves the category empty before the AI has categorized the line', async () => {
    const pending: VoucherGroupRead = {
      ...VOUCHER,
      lines: [line({ status: 'uncategorized', level_1: null, level_2: null, level_3: null })],
    }
    setup({ result: { items: [pending], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Figma Organization, 12 seats')

    const category = screen.getByRole('columnheader', { name: 'Spend category' })
    const index = [...(category.closest('tr')?.children ?? [])].indexOf(category)
    const row = screen.getByText('Figma Organization, 12 seats').closest('tr')
    expect(row?.children[index]?.textContent).toBe('—')
  })

  it('drops a level the categorizer did not fill rather than showing a gap', async () => {
    const partial: VoucherGroupRead = {
      ...VOUCHER,
      lines: [line({ level_1: 'Indirect', level_2: 'Legal', level_3: null })],
    }
    setup({ result: { items: [partial], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Figma Organization, 12 seats')

    const row = screen.getByText('Figma Organization, 12 seats').closest('tr')
    // "Indirect › Legal", not "Indirect › Legal ›" with a dangling separator.
    expect(row?.textContent).toContain('Legal')
    expect(row?.textContent).not.toMatch(/›\s*$/)
  })

  it('lines every row up to the same width, rather than a column short', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Figma Organization, 12 seats')

    // Cells carry colSpans, so width has to be counted by span rather than by
    // cell. Short by one and a line's amount lands under the wrong header.
    const width = (row: Element | null | undefined) =>
      [...(row?.querySelectorAll('th, td') ?? [])].reduce(
        (n, cell) => n + ((cell as HTMLTableCellElement).colSpan || 1),
        0,
      )
    const voucherHeader = document.querySelector('thead tr')
    // The voucher *body* row too, not only its header: a line row carries one
    // more column than a voucher row, and widening the header alone would leave
    // every group total sitting one column left of the amounts beneath it.
    const voucherRow = screen.getByText('V-1042').closest('tr')
    const lineHeader = screen.getByRole('columnheader', { name: 'Quantity' }).closest('tr')
    const lineRow = screen.getByText('Figma Organization, 12 seats').closest('tr')

    expect(width(voucherHeader)).toBeGreaterThan(0)
    expect(width(voucherRow)).toBe(width(voucherHeader))
    expect(width(lineHeader)).toBe(width(voucherHeader))
    expect(width(lineRow)).toBe(width(voucherHeader))
  })

  it('never prints a zero for a line that carries no amount', async () => {
    const zeroed: VoucherGroupRead = {
      ...VOUCHER,
      lines: [line({ amount: null, base_amount: null })],
    }
    setup({ result: { items: [zeroed], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Figma Organization, 12 seats')

    // Exact match: /0\.00/ also matches inside "1,200.00".
    expect(screen.queryByText('DKK 0.00')).toBeNull()
  })

  it('shows the lines, whose sum the group figure is not', async () => {
    setup({ result: { items: [SPLIT], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-SPLIT/ }))
    await screen.findByText('Figma seats')

    expect(screen.getByText('DKK 500.00')).toBeTruthy()
    expect(screen.getByText('DKK 400.00')).toBeTruthy()
    // The group states its net spend, computed server-side from the *postings*
    // — which is exactly why the column is not called Total.
    expect(screen.getByText('DKK 900.00')).toBeTruthy()
  })

  it('states a line’s unit price as it was stated, currency and all', async () => {
    const priced: VoucherGroupRead = {
      ...VOUCHER,
      lines: [line({ description: 'Monitors', quantity: '2', unit_price: '1600.00' })],
    }
    setup({ result: { items: [priced], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Monitors')

    const header = screen.getByRole('columnheader', { name: 'Unit price' })
    const index = [...(header.closest('tr')?.children ?? [])].indexOf(header)
    const row = screen.getByText('Monitors').closest('tr')
    expect(row?.children[index]?.textContent).toContain('1,600.00')
  })

  it('shows no unit price where the source stated none', async () => {
    // Billy states an amount and no unit price at all, so this is the norm.
    const unpriced: VoucherGroupRead = {
      ...VOUCHER,
      lines: [line({ description: 'Monitors', unit_price: null })],
    }
    setup({ result: { items: [unpriced], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Monitors')

    const header = screen.getByRole('columnheader', { name: 'Unit price' })
    const index = [...(header.closest('tr')?.children ?? [])].indexOf(header)
    const row = screen.getByText('Monitors').closest('tr')
    expect(row?.children[index]?.textContent).toBe('—')
  })

  it('states the unit a line’s quantity is counted in', async () => {
    const hourly: VoucherGroupRead = {
      ...VOUCHER,
      lines: [line({ description: 'Consulting', quantity: '12', unit: 'hours' })],
    }
    setup({ result: { items: [hourly], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Consulting')

    // A bare 12 against "Consulting" is twelve hours or twelve days.
    const unit = screen.getByRole('columnheader', { name: 'Unit' })
    const index = [...(unit.closest('tr')?.children ?? [])].indexOf(unit)
    const row = screen.getByText('Consulting').closest('tr')
    expect(row?.children[index]?.textContent).toBe('hours')
  })

  it('substitutes no unit where the source stated none', async () => {
    // "pcs" assumed over an hourly line is a wrong figure stated confidently.
    const unitless: VoucherGroupRead = {
      ...VOUCHER,
      lines: [line({ description: 'Consulting', quantity: '12', unit: null })],
    }
    setup({ result: { items: [unitless], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Consulting')

    const unit = screen.getByRole('columnheader', { name: 'Unit' })
    const index = [...(unit.closest('tr')?.children ?? [])].indexOf(unit)
    const row = screen.getByText('Consulting').closest('tr')
    expect(row?.children[index]?.textContent).toBe('—')
  })

  it('prefers the invoice number read from the document', () => {
    // The ERP posted the bill id, which is not an invoice number at all.
    setup({
      result: {
        items: [{ ...VOUCHER, invoice_number: '615d7cd6b6e9528db0b9b3',
                  document_invoice_number: '2026-0412' }],
        page: 1, page_size: 25, total: 1,
      },
    })

    expect(screen.getByText('2026-0412')).toBeTruthy()
  })

  it('keeps the posted number reachable when the two disagree', () => {
    setup({
      result: {
        items: [{ ...VOUCHER, invoice_number: '615d7cd6b6e9528db0b9b3',
                  document_invoice_number: '2026-0412' }],
        page: 1, page_size: 25, total: 1,
      },
    })

    // A disagreement means the ERP's number is wrong or the scan belongs to
    // another invoice — either is worth seeing, so it is not discarded.
    const cell = screen.getByLabelText(/read from the document/i)
    expect(cell.getAttribute('aria-label')).toContain('615d7cd6b6e9528db0b9b3')
    expect(cell.getAttribute('tabindex')).toBe('0')
  })

  it('falls back to the posted number before the document has been read', () => {
    setup({
      result: {
        items: [{ ...VOUCHER, invoice_number: 'INV-77', document_invoice_number: null }],
        page: 1, page_size: 25, total: 1,
      },
    })

    expect(screen.getByText('INV-77')).toBeTruthy()
    expect(screen.queryByLabelText(/read from the document/i)).toBeNull()
  })

  it('shows no invoice number where neither exists', () => {
    setup({
      result: {
        items: [{ ...VOUCHER, invoice_number: null, document_invoice_number: null }],
        page: 1, page_size: 25, total: 1,
      },
    })

    expect(screen.queryByLabelText(/read from the document/i)).toBeNull()
  })

  it('marks a line that stands in for a posting', async () => {
    const standin: VoucherGroupRead = {
      ...VOUCHER,
      doc_status: 'not_applicable',
      lines: [line({ description: 'Kontorartikler', origin: 'entry_fallback' })],
    }
    setup({ result: { items: [standin], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Kontorartikler')

    // The explanation is the whole content of the mark, so it has to reach a
    // keyboard and a screen-reader user, not only a pointer.
    const mark = screen.getByLabelText(/stands in for a ledger posting/i)
    expect(mark.getAttribute('tabindex')).toBe('0')
  })

  it('leaves an extracted line unmarked, so the mark still means something', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Figma Organization, 12 seats')

    expect(screen.queryByLabelText(/stands in for a ledger posting/i)).toBeNull()
  })

  it('gives a voucher with no lines no expand affordance, but still opens it', () => {
    // A journal entry has no invoice behind it. Its postings live on the
    // panel's Postings tab, which the row still opens.
    const linesless: VoucherGroupRead = { ...VOUCHER, lines: [], doc_status: null }
    const props = setup({ result: { items: [linesless], page: 1, page_size: 25, total: 1 } })

    expect(screen.queryByRole('button', { name: /Expand voucher/ })).toBeNull()
    fireEvent.click(screen.getByText('V-1042'))
    expect(props.onSelectEntry).toHaveBeenCalled()
  })

  it('renders a refund as negative spend', () => {
    const refund: VoucherGroupRead = { ...VOUCHER, voucher_id: 'CN-1', amount: '-3200.00' }
    setup({ result: { items: [refund], page: 1, page_size: 25, total: 1 } })
    expect(screen.getByText(/-.*3,200\.00/)).toBeTruthy()
  })

  it('shows no amount for a voucher that spent nothing', () => {
    const payment: VoucherGroupRead = { ...VOUCHER, voucher_id: 'PAY-1', amount: null }
    setup({ result: { items: [payment], page: 1, page_size: 25, total: 1 } })
    // An em dash, not a 0.00 that reads like a figure.
    expect(screen.queryByText(/0\.00/)).toBeNull()
  })

  it('badges a voucher containing a failed posting', () => {
    setup({ result: { items: [LONE], page: 1, page_size: 25, total: 1 } })
    expect(screen.getAllByText('failed').length).toBeGreaterThan(0)
  })

  it('pages through the server envelope', () => {
    const props = setup({
      result: { items: [VOUCHER], page: 1, page_size: 1, total: 3 },
    })
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    expect(props.onPageChange).toHaveBeenCalledWith(2)
  })
})

describe('EntriesPanel — a line is labelled by its name', () => {
  const withLines = (first: Partial<InvoiceLineRead>) => ({
    result: {
      items: [{ ...SPLIT, lines: [line({ id: 'sl1', sequence: 0, ...first })] }],
      page: 1, page_size: 25, total: 1,
    },
  })

  it('shows the item name, not the description, when both exist', () => {
    setup(withLines({ item_name: 'Figma Organization seat', description: 'Annual, 12 seats' }))
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-SPLIT/ }))

    expect(screen.getByText('Figma Organization seat')).toBeTruthy()
    // The prose belongs on the line card, not in a table cell.
    expect(screen.queryByText('Annual, 12 seats')).toBeNull()
  })

  it('falls back to the description when the line has no name', () => {
    // Every line stored before the split has its text in `description`, and a
    // blank row would make them all look like extraction failures.
    setup(withLines({ item_name: null, description: 'Cloud hosting March' }))
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-SPLIT/ }))

    expect(screen.getByText('Cloud hosting March')).toBeTruthy()
  })

  it('marks a line with neither rather than leaving the cell blank', () => {
    setup(withLines({ item_name: null, description: null }))
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-SPLIT/ }))

    expect(screen.getByText('Unnamed line')).toBeTruthy()
  })
})

describe('EntriesPanel — filters', () => {
  // Note: choosing from a `Select` popup is not exercised here. Base UI's
  // select only hit-tests its first option under jsdom's zero-size layout, so
  // a click on any later option is swallowed — an environment limit, not a
  // product one. The option lists are asserted instead, and the date range
  // (a Popover-based control that does work) covers the change wiring.
  it('offers each company and entry type as an option', async () => {
    setup()
    fireEvent.click(screen.getAllByRole('combobox')[0])

    const options = await screen.findAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(['All companies', 'Acme A/S'])
  })

  it('reports a date-range choice as a filter change', async () => {
    const props = setup()
    fireEvent.click(screen.getAllByText('Any date')[0])

    const day = (await screen.findAllByRole('gridcell')).find((c) => c.textContent === '15')
    fireEvent.click(day!.querySelector('button') ?? day!)

    await waitFor(() => expect(props.onFiltersChange).toHaveBeenCalledTimes(1))
    // Serialized as the API's own `from` date, not a Date object or an ISO datetime.
    expect(props.onFiltersChange).toHaveBeenCalledWith({ from: expect.stringMatching(/^\d{4}-\d{2}-15$/) })
  })

  it('passes a supplier search straight through to the caller', () => {
    const props = setup()
    fireEvent.change(screen.getByPlaceholderText('All suppliers'), { target: { value: 'cont' } })
    expect(props.onVendorSearch).toHaveBeenCalledWith('cont', expect.anything())
  })

  it('lines every company option up on one left edge', async () => {
    // The flag and the label sit inside Base UI's `ItemText`, not the item's
    // own flex container — so an inline spacer collapses to nothing and "All
    // companies" ends up a flag's width left of every company beneath it.
    setup()

    fireEvent.click(screen.getByRole('combobox', { name: /company/i }))
    const all = await screen.findByRole('option', { name: 'All companies' })
    const acme = screen.getByRole('option', { name: /Acme/ })

    const leading = (option: HTMLElement) =>
      option.querySelector('span > span:first-child')?.className ?? ''

    // Both rows open with a box of the same size: a flag, or a spacer standing
    // in for one.
    expect(leading(all)).toContain('size-5')
    expect(leading(acme)).toContain('size-5')
  })

  it('offers filter options by their display name, never a raw key', async () => {
    setup({ entryTypes: ['purchase_invoice', 'journal_entry'] })

    fireEvent.click(screen.getByRole('combobox', { name: /entry type/i }))

    expect(await screen.findByRole('option', { name: 'Purchase invoice' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Journal entry' })).toBeTruthy()
    // The underscored key must not survive anywhere in the list.
    expect(screen.queryByRole('option', { name: /purchase_invoice/ })).toBeNull()
  })

  it('shows the display name on the trigger too, not only in the list', () => {
    // Humanizing the list while the trigger still reads `entry_fallback` is
    // worse than never humanizing at all: the two disagree in front of the user.
    setup({ filters: { origin: 'entry_fallback' } })

    expect(screen.getByText('From posting')).toBeTruthy()
    expect(screen.queryByText('entry_fallback')).toBeNull()
  })

  it('gives every filter control the same width', () => {
    // Six different widths turned a row of peers into a ragged edge. An option
    // too long for the shared width wraps inside the popup rather than driving
    // every other control wider to match it.
    setup()

    // The controls themselves, not the decoration inside them: a date picker
    // nests a `w-0` sizing helper that is not a control and would fail this on
    // a technicality.
    const controls = [...document.querySelectorAll('label button, label input')].filter((el) =>
      /\bw-\d+\b/.test(el.className),
    )
    const widths = new Set(
      controls.map((el) => /\bw-\d+\b/.exec(el.className)?.[0]),
    )

    expect(controls.length).toBeGreaterThanOrEqual(6)
    expect([...widths]).toHaveLength(1)
  })

  it('offers a clear control only once a filter is set', () => {
    const { onClearFilters } = setup({ filters: { status: 'failed' } })
    fireEvent.click(screen.getByRole('button', { name: /Clear filters/ }))
    expect(onClearFilters).toHaveBeenCalled()
  })

  it('does not treat the page number as a filter', () => {
    setup({ filters: { page: 2 } })
    expect(screen.queryByRole('button', { name: /Clear filters/ })).toBeNull()
  })
})

describe('EntriesPanel — states', () => {
  it('shows placeholders while loading', () => {
    const { container } = render(
      <EntriesPanel
        {...setupProps({ loading: true, result: undefined })}
      />,
    )
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('distinguishes "nothing synced" from "nothing matches"', () => {
    const { unmount } = render(
      <EntriesPanel {...setupProps({ result: { items: [], page: 1, page_size: 25, total: 0 } })} />,
    )
    expect(screen.getByText(/No ERP data synced yet/)).toBeTruthy()
    unmount()

    render(
      <EntriesPanel
        {...setupProps({
          result: { items: [], page: 1, page_size: 25, total: 0 },
          filters: { status: 'failed' },
        })}
      />,
    )
    expect(screen.getByText(/No entries match these filters/)).toBeTruthy()
  })

  it('explains that a supplier filter excludes unlinked postings', () => {
    render(
      <EntriesPanel
        {...setupProps({
          result: { items: [], page: 1, page_size: 25, total: 0 },
          filters: { vendor_id: 'v1' },
        })}
      />,
    )
    expect(screen.getByText(/carry no supplier/)).toBeTruthy()
  })

  it('shows an error state instead of an empty table', () => {
    render(<EntriesPanel {...setupProps({ error: true, result: undefined })} />)
    expect(screen.getByText(/Couldn’t load your entries/)).toBeTruthy()
  })
})

/**
 * A voucher posted in EUR and USD, both converted into the company's DKK. As
 * posted these two cannot be added at all — converted, they are one figure.
 */
const CONVERTED_LINE = () =>
  line({
    id: 'cl1', description: 'Converted line', amount: '100.00', currency: 'EUR',
    base_currency: 'DKK', base_amount: '746.00', fx_rate: '7.46',
    fx_rate_date: '2026-02-02',
  })

const CONVERTED_MIX: VoucherGroupRead = {
  ...VOUCHER,
  voucher_id: 'V-MIX',
  amount: '1434.00',
  debit_total: '1434.00',
  credit_total: '0',
  currency: 'DKK',
  unconverted_count: 0,
  entry_count: 2,
  entries: [
    entry({
      id: 'm1', voucher_id: 'V-MIX', currency: 'EUR', debit_amount: '100.00',
      base_debit_amount: '746.00', fx_rate: '7.46', fx_rate_date: '2026-02-02',
    }),
    entry({
      id: 'm2', voucher_id: 'V-MIX', currency: 'USD', debit_amount: '100.00',
      base_debit_amount: '688.00', fx_rate: '6.88', fx_rate_date: '2026-02-02',
    }),
  ],
}

/** One posting no rate was available for, alongside one that converted. The
 *  line mirrors it, since the expanded table is what shows lines. */
const PARTLY_UNCONVERTED: VoucherGroupRead = {
  ...VOUCHER,
  voucher_id: 'V-GAP',
  lines: [
    line({
      id: 'gl1', description: 'Unconverted line', amount: '500.00', currency: 'GBP',
      base_currency: null, base_amount: null, fx_rate: null, fx_rate_date: null,
    }),
  ],
  amount: '1200.00',
  debit_total: '1200.00',
  currency: 'DKK',
  unconverted_count: 1,
  entry_count: 2,
  entries: [
    entry({ id: 'g1', voucher_id: 'V-GAP' }),
    entry({
      id: 'g2', voucher_id: 'V-GAP', currency: 'GBP', debit_amount: '500.00',
      base_currency: null, base_debit_amount: null, fx_rate: null, fx_rate_date: null,
    }),
  ],
}

describe('EntriesPanel — currency conversion', () => {
  it('gives a mixed-currency voucher one total in the company’s currency', () => {
    setup({ result: { items: [CONVERTED_MIX], page: 1, page_size: 25, total: 1 } })

    expect(screen.getByText('DKK 1,434.00')).toBeTruthy()
    // Converted, so there is nothing "mixed" left to warn about.
    expect(screen.queryByText('Mixed currencies')).toBeNull()
  })

  it('still refuses to sum postings that could not be converted', () => {
    setup({ result: { items: [MIXED], page: 1, page_size: 25, total: 1 } })

    expect(screen.getByText('Mixed currencies')).toBeTruthy()
  })

  it('lets a converted line explain itself', async () => {
    setup({
      result: {
        items: [{ ...CONVERTED_MIX, lines: [CONVERTED_LINE()] }],
        page: 1, page_size: 25, total: 1,
      },
    })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-MIX/ }))

    // The line shows the company's currency…
    const converted = await screen.findByText('DKK 746.00')
    // …and carries what it was, at what rate, from which publication — in the
    // accessible name, so it is not hover-only.
    const label = converted.getAttribute('aria-label') ?? ''
    expect(label).toContain('€100.00')
    expect(label).toContain('7.46 DKK/EUR')
    expect(label).toContain('2 Feb 2026')
  })

  it('offers the explanation to the keyboard, not only the mouse', async () => {
    setup({
      result: {
        items: [{ ...CONVERTED_MIX, lines: [CONVERTED_LINE()] }],
        page: 1, page_size: 25, total: 1,
      },
    })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-MIX/ }))

    const converted = await screen.findByText('DKK 746.00')
    expect(converted.getAttribute('tabindex')).toBe('0')
  })

  it('does not dress a same-currency posting up as a conversion', async () => {
    // One spend posting, so the group does not expand — its total is the
    // figure on show, and it is not a conversion: a rate of 1 has nothing to
    // disclose.
    setup()

    const amounts = await screen.findAllByText('DKK 1,200.00')
    expect(amounts.length).toBeGreaterThan(0)
    expect(amounts.every((el) => el.getAttribute('tabindex') === null)).toBe(true)
  })

  it('marks an unconverted line in its own currency', async () => {
    setup({ result: { items: [PARTLY_UNCONVERTED], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-GAP/ }))

    // Shown as posted and marked — never as 0.00, and never as DKK.
    const unconverted = await screen.findByLabelText(/£500\.00, not converted/)
    expect(unconverted.textContent).toContain('£500.00*')
  })

  it('says when a total leaves postings out', async () => {
    setup({ result: { items: [PARTLY_UNCONVERTED], page: 1, page_size: 25, total: 1 } })

    const marker = screen.getByText('+1*')
    expect(marker.getAttribute('aria-label')).toContain('not included in this total')
  })

  it('shows no total when nothing in the voucher converted', () => {
    setup({
      result: {
        items: [{ ...PARTLY_UNCONVERTED, currency: null, amount: null,
                  debit_total: null, credit_total: null, unconverted_count: 2 }],
        page: 1, page_size: 25, total: 1,
      },
    })

    expect(screen.getByText('Not converted')).toBeTruthy()
    expect(screen.queryByText(/0\.00/)).toBeNull()
  })
})

describe('EntriesPanel — voucher panel', () => {
  it('opens the panel for the voucher named in the URL', () => {
    render(<EntriesPanel {...setupProps({ filters: { voucher: '4821' }, voucherDetail: DETAIL })} />)
    expect(screen.getByLabelText('Voucher detail')).toBeTruthy()
  })

  it('stays closed when neither a voucher nor an entry is named', () => {
    setup()
    expect(screen.queryByLabelText('Voucher detail')).toBeNull()
  })

  it('opens when only an entry is named — the voucherless case', () => {
    render(<EntriesPanel {...setupProps({ filters: { entry: 'e9' }, voucherDetail: DETAIL })} />)
    expect(screen.getByLabelText('Voucher detail')).toBeTruthy()
  })

  it('opens the voucher when the row itself is pressed, not only its number', () => {
    const onSelectEntry = vi.fn()
    render(<EntriesPanel {...setupProps({ onSelectEntry })} />)
    // The supplier cell is not a control. Pressing it is pressing the row, which
    // is what a reader does — the voucher number is a small target in a wide row,
    // and the row already carries a pointer cursor promising it can be pressed.
    fireEvent.click(screen.getByText('Contoso ApS'))
    expect(onSelectEntry).toHaveBeenCalledWith({ voucher: 'V-1042', entry: 'e1' })
  })

  it('expands without opening the panel, since those are different actions', () => {
    const onSelectEntry = vi.fn()
    render(<EntriesPanel {...setupProps({ onSelectEntry })} />)
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    // Revealing the lines in place is not a request to open the panel over them.
    expect(onSelectEntry).not.toHaveBeenCalled()
  })

  it('opens a line from anywhere in its row, not only its description', async () => {
    const onSelectEntry = vi.fn()
    render(
      <EntriesPanel
        {...setupProps({
          result: { items: [SPLIT], page: 1, page_size: 25, total: 1 },
          onSelectEntry,
        })}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-SPLIT/ }))
    await screen.findByText('Flights to Berlin')
    // The line's own amount cell — evidence, not a control.
    fireEvent.click(screen.getByText('DKK 400.00'))

    expect(onSelectEntry).toHaveBeenCalledWith({
      voucher: 'V-SPLIT', entry: 's1', tab: 'lines', line: 'sl2',
    })
  })

  it('asks to open a voucher by its id, and by entry id when it has none', () => {
    const onSelectEntry = vi.fn()
    render(<EntriesPanel {...setupProps({ onSelectEntry })} />)
    fireEvent.click(screen.getAllByRole('button', { name: /view voucher/i })[0])
    expect(onSelectEntry).toHaveBeenCalledWith({ voucher: 'V-1042', entry: 'e1' })
  })

  it('opens a line inside an expanded voucher as that voucher, on its Lines tab', async () => {
    const onSelectEntry = vi.fn()
    render(
      <EntriesPanel
        {...setupProps({
          result: { items: [SPLIT], page: 1, page_size: 25, total: 1 },
          onSelectEntry,
        })}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-SPLIT/ }))
    fireEvent.click(await screen.findByText('Flights to Berlin'))

    // The voucher, addressed by its id — and opened on the tab that shows the
    // row the reader actually activated.
    expect(onSelectEntry).toHaveBeenCalledWith({
      voucher: 'V-SPLIT', entry: 's1', tab: 'lines', line: 'sl2',
    })
  })

  it('reports dismissal back to the owner by clearing the selection', async () => {
    const onSelectEntry = vi.fn()
    render(
      <EntriesPanel
        {...setupProps({
          filters: { voucher: '4821' },
          voucherDetail: DETAIL,
          onSelectEntry,
        })}
      />,
    )
    await screen.findByLabelText('Voucher detail')
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })

    await waitFor(() => expect(onSelectEntry).toHaveBeenCalledWith({}))
  })

  it('shows a loading skeleton while the voucher detail is in flight', () => {
    render(
      <EntriesPanel
        {...setupProps({ filters: { voucher: '4821' }, voucherDetail: undefined, voucherLoading: true })}
      />,
    )
    expect(document.body.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('renders the audit feed passed to it', () => {
    render(
      <EntriesPanel
        {...setupProps({
          filters: { voucher: '4821', tab: 'activity' },
          voucherDetail: DETAIL,
          tab: 'activity',
          auditRows: [
            {
              id: 'a1',
              entity_type: 'invoice_line',
              entity_id: 'l1',
              entity_label: 'Office chairs',
              action: 'verify',
              actor: 'user_123',
              changes: null,
              created_at: '2026-07-02T09:05:00Z',
            },
          ],
        })}
      />,
    )
    expect(screen.getByText(/Office chairs/)).toBeTruthy()
  })

  it('reports a tab click back to the owner', () => {
    const onTabChange = vi.fn()
    render(
      <EntriesPanel
        {...setupProps({ filters: { voucher: '4821' }, voucherDetail: DETAIL, onTabChange })}
      />,
    )
    fireEvent.click(screen.getByRole('tab', { name: /postings/i }))
    expect(onTabChange).toHaveBeenCalledWith('postings')
  })

  it('forwards a line verification to the owner', async () => {
    const onVerifyLine = vi.fn().mockResolvedValue(undefined)
    render(
      <EntriesPanel
        {...setupProps({
          filters: { voucher: '4821' },
          tab: 'lines' as const,
          voucherDetail: { ...DETAIL, invoice: invoiceDetail({ lines: [
            line({
              description: 'Office chairs', quantity: '2', unit_price: '450.00',
              amount: '900.00', base_amount: '900.00',
              level_1: 'Facilities', level_2: 'Furniture', level_3: 'Office chairs',
              account_code: '6100', account_name: 'Office equipment',
              confidence: '0.62', rationale: null,
            }),
          ] }) },
          onVerifyLine,
        })}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /accept/i }))
    expect(onVerifyLine).toHaveBeenCalledWith('l1', {})
  })
})
