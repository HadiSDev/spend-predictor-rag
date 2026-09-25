import type { VoucherSelection } from './api/entries'
import type { EntryFilters, LineOrigin, VoucherTab } from './api/types'

/** Read one search key, dropping empty values. */
function str(value: unknown): string | undefined {
  return typeof value === 'string' && value !== '' ? value : undefined
}

const VOUCHER_TABS: ReadonlyArray<VoucherTab> = [
  'lines',
  'details',
  'postings',
  'activity',
]

/** The line provenances worth filtering by. */
export const LINE_ORIGINS: ReadonlyArray<LineOrigin> = [
  'document_ai',
  'erp',
  'entry_fallback',
  'human',
]

/** Read the origin, ignoring unknown values. */
function origin(value: unknown): LineOrigin | undefined {
  return typeof value === 'string' &&
    (LINE_ORIGINS as ReadonlyArray<string>).includes(value)
    ? (value as LineOrigin)
    : undefined
}

/** Read the tab, ignoring unknown values. */
function tab(value: unknown): VoucherTab | undefined {
  return typeof value === 'string' &&
    (VOUCHER_TABS as ReadonlyArray<string>).includes(value)
    ? (value as VoucherTab)
    : undefined
}

/** Parse the Entries route's search params. */
export function validateEntrySearch(
  search: Record<string, unknown>,
): EntryFilters {
  const page = Number(search.page)
  return {
    company_id: str(search.company_id),
    entry_type: str(search.entry_type),
    status: str(search.status),
    vendor_id: str(search.vendor_id),
    origin: origin(search.origin),
    from: str(search.from),
    to: str(search.to),
    page: Number.isInteger(page) && page > 1 ? page : undefined,
    voucher: str(search.voucher),
    entry: str(search.entry),
    tab: tab(search.tab),
  }
}

/** Apply a filter change. */
export function applyFilterChange(
  filters: EntryFilters,
  changes: Partial<EntryFilters>,
): EntryFilters {
  return {
    ...filters,
    ...changes,
    page: undefined,
    voucher: undefined,
    entry: undefined,
    tab: undefined,
  }
}

/** Apply a request to open (or close) the voucher panel. */
export function applyVoucherSelection(
  filters: EntryFilters,
  selection: VoucherSelection,
): EntryFilters {
  const open = selection.voucher !== undefined || selection.entry !== undefined
  return {
    ...filters,
    voucher: selection.voucher,
    entry: selection.entry,
    tab: open ? (selection.tab ?? filters.tab) : undefined,
  }
}

/** Entry types the API never lists. */
const EXCLUDED_ENTRY_TYPES: ReadonlyArray<string> = ['payment']

/** The entry types worth offering as a filter. */
export function listableEntryTypes(types: Iterable<string>): Array<string> {
  return [...new Set(types)]
    .filter((t) => !EXCLUDED_ENTRY_TYPES.includes(t))
    .sort()
}
