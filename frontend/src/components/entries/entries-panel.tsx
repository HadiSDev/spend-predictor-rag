import * as React from 'react'
import { Button, Card, Pagination, Skeleton } from '#/components/ui'
import type { VoucherKey } from '#/lib/entries'
import type {
  CompanyRead,
  EntryFilters,
  InvoiceLineUpdate,
  InvoiceUpdate,
  LineCorrections,
  Page,
  SpendCategoryRead,
  VendorRead,
  VoucherAuditRead,
  VoucherDetailRead,
  VoucherGroupRead,
  VoucherTab,
} from '#/lib/types'
import { FilterBar } from './filter-bar'
import { VoucherDrawer } from './voucher-drawer'
import { VoucherTable } from './voucher-table'

/** The filter keys that narrow results; `page` is navigation, not a filter. */
const FILTER_KEYS = ['company_id', 'entry_type', 'status', 'vendor_id', 'from', 'to'] as const

export function hasActiveFilters(filters: EntryFilters): boolean {
  return FILTER_KEYS.some((key) => filters[key] !== undefined)
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-12 rounded-md" />
      ))}
    </div>
  )
}

function EmptyState({
  filters,
  onClear,
}: {
  filters: EntryFilters
  onClear: () => void
}) {
  if (!hasActiveFilters(filters)) {
    return (
      <Card className="p-8 text-center">
        <h2 className="font-display text-base font-medium">No ERP data synced yet</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          Once a sync runs against a connected ERP, its postings appear here.
        </p>
      </Card>
    )
  }
  return (
    <Card className="p-8 text-center">
      <h2 className="font-display text-base font-medium">No entries match these filters</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        Try widening the date range or clearing a filter.
        {filters.vendor_id !== undefined ? (
          <>
            {' '}
            Note that postings not linked to an invoice carry no supplier, so a supplier filter
            excludes them.
          </>
        ) : null}
      </p>
      <div className="mt-4">
        <Button variant="outline" onClick={onClear}>
          Clear filters
        </Button>
      </div>
    </Card>
  )
}

export interface EntriesPanelProps {
  result: Page<VoucherGroupRead> | undefined
  loading: boolean
  error: boolean
  filters: EntryFilters
  companies: Array<CompanyRead>
  vendors: Array<VendorRead>
  entryTypes: Array<string>
  onFiltersChange: (changes: Partial<EntryFilters>) => void
  onClearFilters: () => void
  onPageChange: (page: number) => void
  onVendorSearch: (query: string) => void
  /** The open voucher's full detail, and its loading state. `undefined`
   *  while in flight — never an empty object. */
  voucherDetail: VoucherDetailRead | undefined
  voucherLoading: boolean
  /** The open voucher's change history, newest first. */
  auditRows: Array<VoucherAuditRead>
  auditLoading: boolean
  /** Which face of the panel is showing — URL state, owned by the route. */
  tab: VoucherTab
  onTabChange: (tab: VoucherTab) => void
  /** Opens the panel for a voucher (or, lacking one, a lone posting). Also
   *  the way the panel is closed: `onSelectEntry({})` clears both. */
  onSelectEntry: (key: VoucherKey) => void
  onVerifyLine: (lineId: string, corrections: LineCorrections) => Promise<void>
  /** The open voucher's company's spend tree. Resolved by the route, so one
   *  request serves every line in the panel. */
  spendTreeNodes: Array<SpendCategoryRead> | null
  /** Where a manager assigns that company's tree, for the no-tree case. */
  companySettingsHref?: string
  onUpdateHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Verify the header, applying any pending edits first. */
  onVerifyHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Correct what a line says was bought — not its category. */
  onUpdateLine: (lineId: string, changes: InvoiceLineUpdate) => Promise<void>
  /** Add a line to the open invoice, and delete one from it. */
  onCreateLine: (invoiceId: string) => Promise<void>
  onDeleteLine: (lineId: string) => Promise<void>
  /** Queue an invoice's document to be read again. */
  onReprocess: (invoiceId: string) => Promise<void>
  /** Whether the signed-in user holds a management role — every write in the
   *  panel requires one, so the actions are offered only where they will work. */
  canManage: boolean
}

/**
 * The Entries page body. Presentational: every query and the URL-backed filter
 * state live in the route, so this can be rendered directly in tests.
 */
export function EntriesPanel({
  result,
  loading,
  error,
  filters,
  companies,
  vendors,
  entryTypes,
  onFiltersChange,
  onClearFilters,
  onPageChange,
  onVendorSearch,
  voucherDetail,
  voucherLoading,
  auditRows,
  auditLoading,
  tab,
  onTabChange,
  onSelectEntry,
  onVerifyLine,
  spendTreeNodes,
  companySettingsHref,
  onUpdateHeader,
  onVerifyHeader,
  onUpdateLine,
  onCreateLine,
  onDeleteLine,
  onReprocess,
  canManage,
}: EntriesPanelProps) {
  const pageCount = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1
  const open = filters.voucher !== undefined || filters.entry !== undefined
  // Local to the panel: whether the Details tab's header editor has edits not
  // yet saved. `VoucherDetailsTab` remounts (`key={invoice.id}`) whenever the
  // open voucher's invoice changes, which fires its cleanup and resets this —
  // so a discard on one voucher never bleeds into the next one opened. Also
  // reset explicitly on close, in case the drawer's content stays mounted
  // through its close animation rather than unmounting immediately.
  const [headerDirty, setHeaderDirty] = React.useState(false)

  return (
    <div className="flex flex-col gap-6">
      <FilterBar
        filters={filters}
        companies={companies}
        vendors={vendors}
        entryTypes={entryTypes}
        onChange={onFiltersChange}
        onClear={onClearFilters}
        onVendorSearch={onVendorSearch}
      />

      {error ? (
        <Card className="p-8 text-center">
          <h2 className="font-display text-base font-medium">Couldn’t load your entries</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            The request to the web API failed. Check that it is running and reachable, then reload.
          </p>
        </Card>
      ) : loading ? (
        <LoadingState />
      ) : !result || result.items.length === 0 ? (
        <EmptyState filters={filters} onClear={onClearFilters} />
      ) : (
        <>
          <VoucherTable groups={result.items} onSelectEntry={onSelectEntry} />
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {result.total} voucher{result.total === 1 ? '' : 's'}
            </p>
            <Pagination page={result.page} pageCount={pageCount} onPageChange={onPageChange} />
          </div>
        </>
      )}

      <VoucherDrawer
        detail={voucherDetail}
        loading={voucherLoading}
        auditRows={auditRows}
        auditLoading={auditLoading}
        tab={tab}
        open={open}
        onTabChange={onTabChange}
        onOpenChange={(next) => {
          if (!next) {
            onSelectEntry({})
            setHeaderDirty(false)
          }
        }}
        onVerifyLine={onVerifyLine}
        spendTreeNodes={spendTreeNodes}
        companySettingsHref={companySettingsHref}
        onUpdateHeader={onUpdateHeader}
        onVerifyHeader={onVerifyHeader}
        onUpdateLine={onUpdateLine}
        onCreateLine={onCreateLine}
        onDeleteLine={onDeleteLine}
        vendors={vendors}
        onReprocess={onReprocess}
        canManage={canManage}
        onHeaderDirtyChange={setHeaderDirty}
        hasUnsavedChanges={headerDirty}
      />
    </div>
  )
}
