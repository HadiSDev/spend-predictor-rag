import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { EntriesPanel } from './entries-panel'
import type { EntriesPanelProps } from './entries-panel'
import type { CompanyRead, ErpEntryRead, VendorRead, VoucherGroupRead } from '#/lib/types'

const ACME: CompanyRead = {
  id: 'c1',
  name: 'Acme A/S',
  country_code: 'DK',
  vat_number: 'DK12345678',
  base_currency: 'DKK',
  is_active: true,
  deactivated_at: null,
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
  debit_total: '30.00',
  entries: [
    entry({ id: 'm1', voucher_id: 'V-MIX', currency: 'DKK', debit_amount: '10.00' }),
    entry({ id: 'm2', voucher_id: 'V-MIX', currency: 'EUR', debit_amount: '20.00' }),
  ],
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
    selectedEntry: undefined,
    selectedEntryLoading: false,
    selectedEntryId: null,
    onSelectEntry: vi.fn(),
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

  it('reveals every posting, plumbing included', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))

    expect(await screen.findByText('Software')).toBeTruthy()
    // VAT and the counterparty are what a reconciliation needs; withholding
    // them was the whole problem.
    expect(screen.getByText('Input VAT')).toBeTruthy()
    expect(screen.getByText('Payables')).toBeTruthy()
  })

  it('opens detail from the row when there is nothing to expand', () => {
    const props = setup({ result: { items: [LONE], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByText('No voucher'))
    expect(props.onSelectEntry).toHaveBeenCalledWith('e9')
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

  it('labels the postings, whose columns the voucher header does not describe', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Software')

    // Without these the account reads under Voucher and the amount under
    // Total Spend — headers that name something else.
    expect(screen.getByRole('columnheader', { name: 'Account' })).toBeTruthy()
    expect(screen.getByRole('columnheader', { name: 'Description' })).toBeTruthy()
    expect(screen.getByRole('columnheader', { name: 'Spend category' })).toBeTruthy()
    // "Amount", not "Total Spend": a VAT or payable posting is not spend.
    expect(screen.getByRole('columnheader', { name: 'Amount' })).toBeTruthy()
  })

  it('shows a posting’s spend category as its full path', async () => {
    const categorized: VoucherGroupRead = {
      ...VOUCHER,
      entries: [
        entry({
          id: 'e1',
          source_invoice_line_id: 'l1',
          spend_category_level_1: 'Indirect',
          spend_category_level_2: 'Legal',
          spend_category_level_3: 'Professional Services',
        }),
        ...VOUCHER.entries.slice(1),
      ],
    }
    setup({ result: { items: [categorized], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Software')

    const row = screen.getByText('Software').closest('tr')
    expect(row?.textContent).toContain('Indirect')
    expect(row?.textContent).toContain('Legal')
    expect(row?.textContent).toContain('Professional Services')
  })

  it('leaves the category empty before the AI has categorized the line', async () => {
    // The default fixture is uncategorized, which is also what every VAT and
    // payable posting looks like — the two are indistinguishable on purpose.
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Software')

    const category = screen.getByRole('columnheader', { name: 'Spend category' })
    const index = [...(category.closest('tr')?.children ?? [])].indexOf(category)
    const row = screen.getByText('Software').closest('tr')
    expect(row?.children[index]?.textContent).toBe('—')
  })

  it('drops a level the categorizer did not fill rather than showing a gap', async () => {
    const partial: VoucherGroupRead = {
      ...VOUCHER,
      entries: [
        entry({ id: 'e1', spend_category_level_1: 'Indirect', spend_category_level_2: 'Legal' }),
        ...VOUCHER.entries.slice(1),
      ],
    }
    setup({ result: { items: [partial], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Software')

    const row = screen.getByText('Software').closest('tr')
    // "Indirect › Legal", not "Indirect › Legal ›" with a dangling separator.
    expect(row?.textContent).toContain('Legal')
    expect(row?.textContent).not.toMatch(/›\s*$/)
  })

  it('lines every row up to the same width, rather than a column short', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-1042/ }))
    await screen.findByText('Software')

    // Cells carry colSpans, so width has to be counted by span rather than by
    // cell. Short by one and a posting's amount lands under the wrong header.
    const width = (row: Element | null | undefined) =>
      [...(row?.querySelectorAll('th, td') ?? [])].reduce(
        (n, cell) => n + ((cell as HTMLTableCellElement).colSpan || 1),
        0,
      )
    const voucherHeader = document.querySelector('thead tr')
    const postingHeader = screen.getByRole('columnheader', { name: 'Account' }).closest('tr')
    const posting = screen.getByText('Software').closest('tr')

    expect(width(voucherHeader)).toBeGreaterThan(0)
    expect(width(postingHeader)).toBe(width(voucherHeader))
    expect(width(posting)).toBe(width(voucherHeader))
  })

  it('never prints a zero for a posting that has no amount on one side', async () => {
    // Connectors send 0.00 rather than null, and "0.00" is a truthy string —
    // the reason every row once printed DKK 0.00.
    setup({ result: { items: [SPLIT], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-SPLIT/ }))
    await screen.findByText('Software')

    // Exact match: /0\.00/ also matches inside "1,200.00".
    expect(screen.queryByText('DKK 0.00')).toBeNull()
  })

  it('shows postings that net to zero, which the group figure is not', async () => {
    setup({ result: { items: [SPLIT], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-SPLIT/ }))
    await screen.findByText('Software')

    // 500 + 400 − 900 = 0, as a balanced voucher must.
    expect(screen.getByText('DKK 500.00')).toBeTruthy()
    expect(screen.getByText('DKK 400.00')).toBeTruthy()
    expect(screen.getByText(/^-\D*900\.00$/)).toBeTruthy()
    // And the group still states its net spend — a different quantity, which
    // is exactly why the column is not called Total.
    expect(screen.getByText('DKK 900.00')).toBeTruthy()
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

describe('EntriesPanel — entry drawer', () => {
  it('opens detail for a posting inside an expanded voucher', async () => {
    const props = setup({ result: { items: [SPLIT], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-SPLIT/ }))
    fireEvent.click(await screen.findByText('Travel'))

    expect(props.onSelectEntry).toHaveBeenCalledWith('s2')
  })

  it('opens detail for a voucherless posting from its row', () => {
    const props = setup({ result: { items: [LONE], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByText('No voucher'))
    expect(props.onSelectEntry).toHaveBeenCalledWith('e9')
  })

  it('renders the failed posting’s error message', async () => {
    const failed = LONE.entries[0]
    render(
      <EntriesPanel
        {...setupProps({ selectedEntryId: failed.id, selectedEntry: failed })}
      />,
    )
    const drawer = await screen.findByRole('dialog')
    expect(within(drawer).getByText('ERP rejected the posting')).toBeTruthy()
    expect(within(drawer).getByText('6200')).toBeTruthy()
  })

  it('reports dismissal back to the owner of the selection', async () => {
    const onSelectEntry = vi.fn()
    render(
      <EntriesPanel
        {...setupProps({ selectedEntryId: 'e1', selectedEntry: entry(), onSelectEntry })}
      />,
    )
    await screen.findByRole('dialog')
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })

    await waitFor(() => expect(onSelectEntry).toHaveBeenCalledWith(null))
  })
})

/** Props for a bare `render` — `setup` renders for us, this one does not. */
function setupProps(overrides: Partial<EntriesPanelProps> = {}): EntriesPanelProps {
  return {
    result: { items: [VOUCHER], page: 1, page_size: 25, total: 1 },
    ...common(),
    entryTypes: ['purchase_invoice'],
    ...overrides,
  }
}

/**
 * A voucher posted in EUR and USD, both converted into the company's DKK. As
 * posted these two cannot be added at all — converted, they are one figure.
 */
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

/** One posting no rate was available for, alongside one that converted. */
const PARTLY_UNCONVERTED: VoucherGroupRead = {
  ...VOUCHER,
  voucher_id: 'V-GAP',
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

  it('lets a converted posting explain itself', async () => {
    setup({ result: { items: [CONVERTED_MIX], page: 1, page_size: 25, total: 1 } })
    fireEvent.click(screen.getByRole('button', { name: /Expand voucher V-MIX/ }))

    // The posting shows the company's currency…
    const converted = await screen.findByText('DKK 746.00')
    // …and carries what it was, at what rate, from which publication — in the
    // accessible name, so it is not hover-only.
    const label = converted.getAttribute('aria-label') ?? ''
    expect(label).toContain('€100.00')
    expect(label).toContain('7.46 DKK/EUR')
    expect(label).toContain('2 Feb 2026')
  })

  it('offers the explanation to the keyboard, not only the mouse', async () => {
    setup({ result: { items: [CONVERTED_MIX], page: 1, page_size: 25, total: 1 } })
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

  it('marks an unconverted posting in its own currency', async () => {
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

describe('EntryDrawer — currency conversion', () => {
  it('shows the conversion as labelled fields', async () => {
    setup({
      selectedEntryId: 'm1',
      selectedEntry: CONVERTED_MIX.entries[0],
      result: { items: [CONVERTED_MIX], page: 1, page_size: 25, total: 1 },
    })

    const drawer = within(await screen.findByLabelText('Entry detail'))
    expect(drawer.getByText('Debit (DKK)')).toBeTruthy()
    expect(drawer.getByText('DKK 746.00')).toBeTruthy()
    expect(drawer.getByText('Exchange rate')).toBeTruthy()
    expect(drawer.getByText('7.46')).toBeTruthy()
    expect(drawer.getByText('Rate date')).toBeTruthy()
    // The posted figure is still right there as the evidence.
    expect(drawer.getByText('€100.00')).toBeTruthy()
  })

  it('says plainly when an entry was not converted', async () => {
    setup({
      selectedEntryId: 'g2',
      selectedEntry: PARTLY_UNCONVERTED.entries[1],
      result: { items: [PARTLY_UNCONVERTED], page: 1, page_size: 25, total: 1 },
    })

    const drawer = within(await screen.findByLabelText('Entry detail'))
    expect(drawer.getByText(/Not converted/)).toBeTruthy()
    expect(drawer.queryByText('Exchange rate')).toBeNull()
  })

  it('adds no conversion rows for a posting already in the company’s currency', async () => {
    setup({ selectedEntryId: 'e1', selectedEntry: entry() })

    const drawer = within(await screen.findByLabelText('Entry detail'))
    expect(drawer.queryByText('Exchange rate')).toBeNull()
    expect(drawer.queryByText('Rate date')).toBeNull()
  })
})
