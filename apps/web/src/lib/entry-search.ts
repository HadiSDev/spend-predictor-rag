import type { VoucherSelection } from './entries'
import type { EntryFilters, LineOrigin, VoucherTab } from './types'

/** Read one search key, dropping empty values so they never reach the URL. */
function str(value: unknown): string | undefined {
  return typeof value === 'string' && value !== '' ? value : undefined
}

const VOUCHER_TABS: ReadonlyArray<VoucherTab> = ['lines', 'details', 'postings', 'activity']

/** The line provenances worth filtering by. See `LineOrigin`. */
export const LINE_ORIGINS: ReadonlyArray<LineOrigin> = [
  'document_ai',
  'erp',
  'entry_fallback',
  'human',
]

/** Read the origin, ignoring anything not a known one — search params are user
 *  input, and an unknown value would make the API 422 or silently return all. */
function origin(value: unknown): LineOrigin | undefined {
  return typeof value === 'string' && (LINE_ORIGINS as ReadonlyArray<string>).includes(value)
    ? (value as LineOrigin)
    : undefined
}

/** Read the tab, ignoring anything not a known tab — search params are user input. */
function tab(value: unknown): VoucherTab | undefined {
  return typeof value === 'string' && (VOUCHER_TABS as ReadonlyArray<string>).includes(value)
    ? (value as VoucherTab)
    : undefined
}

/**
 * Parse the Entries route's search params.
 *
 * Filter state lives in the URL, not in component state — a filtered view is
 * then linkable, survives a reload, and works with back/forward. Unset filters
 * come back as `undefined` rather than `''`, which is what keeps them out of
 * the URL; `page` 1 is likewise the absence of a page param, not `page=1`.
 */
export function validateEntrySearch(search: Record<string, unknown>): EntryFilters {
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

/**
 * Apply a filter change. Any filter change returns to page 1 — narrowing a
 * filter while on page 7 otherwise strands the user on an empty page that
 * reads as "no results". It also closes the voucher panel: the open voucher
 * may not survive the new filter, and leaving it open would show detail for a
 * row that is no longer in the (re-filtered) list.
 */
export function applyFilterChange(
  filters: EntryFilters,
  changes: Partial<EntryFilters>,
): EntryFilters {
  return { ...filters, ...changes, page: undefined, voucher: undefined, entry: undefined, tab: undefined }
}

/**
 * Apply a request to open (or close) the voucher panel.
 *
 * The filters are untouched — a selection narrows nothing — but the tab is
 * **taken from the selection when it states one**. That is the whole point: a
 * reader who pressed a line row is asking to see lines, and an opened panel
 * that shows a different face has covered the row they activated with
 * something else. Lacking a stated tab, the one in view stays, so opening the
 * next voucher does not throw the reader back to Details.
 *
 * Closing (`{}`) clears the tab as well, rather than leaving `tab=lines` in the
 * URL of a page with no panel open.
 */
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

/**
 * Entry types the API never lists. Mirrors `_EXCLUDED_ENTRY_TYPES` in
 * `web_api/routers/erp_entries.py` — a payment settles an invoice already
 * accounted for, so it is noise in a spend tool.
 *
 * Duplicated here for one reason: the type options are derived from
 * `entries-summary`, which reports over *all* entries, so without this the
 * filter would offer a value that can only ever return an empty table.
 */
const EXCLUDED_ENTRY_TYPES: ReadonlyArray<string> = ['payment']

/**
 * The entry types worth offering as a filter: those the org actually has, minus
 * the ones no listing will return.
 */
export function listableEntryTypes(types: Iterable<string>): Array<string> {
  return [...new Set(types)].filter((t) => !EXCLUDED_ENTRY_TYPES.includes(t)).sort()
}
