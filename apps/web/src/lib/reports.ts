import { queryOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type { CategorySpendRow, EntrySummaryRow, Report } from './types'

/**
 * Ledger totals per entry type (`GET /reports/entries-summary`), in the
 * company's own currency.
 *
 * `currency_mode` is sent explicitly even though `base` is the server default —
 * these figures are labelled with the currency the row reports, so the mode is
 * part of what the caller is asking for, not an incidental default.
 */
export function entriesSummaryOptions(api: ApiClient) {
  return queryOptions({
    queryKey: ['reports', 'entries-summary', { currency_mode: 'base' }],
    queryFn: () =>
      api.get<Report<EntrySummaryRow>>('/api/v1/reports/entries-summary', {
        currency_mode: 'base',
      }),
  })
}

/** Categorized spend grouped by level-2 category (`GET /reports/spend-by-category`). */
export function spendByCategoryOptions(api: ApiClient) {
  return queryOptions({
    queryKey: ['reports', 'spend-by-category', { level: 'level_2', currency_mode: 'base' }],
    queryFn: () =>
      api.get<Report<CategorySpendRow>>('/api/v1/reports/spend-by-category', {
        level: 'level_2',
        currency_mode: 'base',
      }),
  })
}
