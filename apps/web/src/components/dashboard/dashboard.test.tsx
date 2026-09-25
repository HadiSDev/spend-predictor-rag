import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DashboardBody } from './body'
import type { CategorySpendRow, EntrySummaryRow } from '#/lib/api/types'

describe('DashboardBody', () => {
  it('renders stat cards and the category table from report data', () => {
    const entryRows: Array<EntrySummaryRow> = [
      {
        entry_type: 'invoice',
        currency: 'DKK',
        debit_total: '1000',
        credit_total: '0',
        net: '1000',
        count: 3,
        unconverted_count: 0,
      },
      {
        entry_type: 'credit_note',
        currency: 'DKK',
        debit_total: '0',
        credit_total: '250',
        net: '-250',
        count: 1,
        unconverted_count: 0,
      },
    ]
    const categoryRows: Array<CategorySpendRow> = [
      {
        level_2: 'Technology',
        level_3: null,
        currency: 'DKK',
        amount_total: '750',
        count: 2,
        unconverted_count: 0,
      },
    ]

    render(<DashboardBody entryRows={entryRows} categoryRows={categoryRows} />)

    expect(screen.getByText('Net ledger · DKK')).toBeTruthy()
    expect(screen.getByText('Transactions')).toBeTruthy()
    expect(screen.getByText('4')).toBeTruthy()
    expect(screen.getByText('Technology')).toBeTruthy()
  })

  it('shows the empty state when both reports are empty', () => {
    render(<DashboardBody entryRows={[]} categoryRows={[]} />)
    expect(screen.getByText('No data yet')).toBeTruthy()
    expect(screen.queryByText('Transactions')).toBeNull()
  })
})
