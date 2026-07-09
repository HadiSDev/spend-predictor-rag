import { queryOptions } from '@tanstack/react-query'
import type { ApiClient } from './api-client'
import type { CategorySpendRow, EntrySummaryRow, Report } from './types'

/** Ledger totals per entry type + currency (`GET /reports/entries-summary`). */
export function entriesSummaryOptions(api: ApiClient) {
  return queryOptions({
    queryKey: ['reports', 'entries-summary'],
    queryFn: () => api.get<Report<EntrySummaryRow>>('/api/v1/reports/entries-summary'),
  })
}

/** Categorized spend grouped by level-2 category (`GET /reports/spend-by-category`). */
export function spendByCategoryOptions(api: ApiClient) {
  return queryOptions({
    queryKey: ['reports', 'spend-by-category', { level: 'level_2' }],
    queryFn: () =>
      api.get<Report<CategorySpendRow>>('/api/v1/reports/spend-by-category', {
        level: 'level_2',
      }),
  })
}
