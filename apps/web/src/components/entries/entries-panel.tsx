import * as React from 'react'
import { Button, Card, Pagination, Skeleton } from '#/components/ui'
import type { VoucherSelection } from '#/lib/api/entries'
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
} from '#/lib/api/types'
import { FilterBar } from './filter-bar'
import { VoucherDrawer } from './voucher/voucher-drawer'
import { VoucherTable } from './voucher-table'

/** The filter keys that narrow results. */
const FILTER_KEYS = [
  'company_id',
  'entry_type',
  'status',
  'vendor_id',
  'from',
  'to',
] as const

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
        <h2 className="font-display text-base font-medium">
          No ERP data synced yet
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          Once a sync runs against a connected ERP, its postings appear here.
        </p>
      </Card>
    )
  }
  return (
    <Card className="p-8 text-center">
      <h2 className="font-display text-base font-medium">
        No entries match these filters
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        Try widening the date range or clearing a filter.
        {filters.vendor_id !== undefined ? (
          <>
            {' '}
            Note that postings not linked to an invoice carry no supplier, so a
            supplier filter excludes them.
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
  /** The open voucher's detail; undefined while loading. */
  voucherDetail: VoucherDetailRead | undefined
  voucherLoading: boolean
  /** The open voucher's change history, newest first. */
  auditRows: Array<VoucherAuditRead>
  auditLoading: boolean
  /** The panel tab being shown. */
  tab: VoucherTab
  onTabChange: (tab: VoucherTab) => void
  /** Opens the panel for a voucher or lone posting; an empty selection closes it. */
  onSelectEntry: (key: VoucherSelection) => void
  onVerifyLine: (lineId: string, corrections: LineCorrections) => Promise<void>
  /** The open voucher's company's spend tree. */
  spendTreeNodes: Array<SpendCategoryRead> | null
  /** Where a manager assigns the company's spend tree. */
  companySettingsHref?: string
  onUpdateHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Verify the header, applying any pending edits first. */
  onVerifyHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Correct what a line says was bought. */
  onUpdateLine: (lineId: string, changes: InvoiceLineUpdate) => Promise<void>
  /** Add a line to, or delete one from, the open invoice. */
  onCreateLine: (invoiceId: string) => Promise<void>
  onDeleteLine: (lineId: string) => Promise<void>
  /** Queue an invoice's document to be read again. */
  onReprocess: (invoiceId: string) => Promise<void>
  /** Whether the signed-in user holds a management role. */
  canManage: boolean
}

/** The Entries page body. */
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
  const pageCount = result
    ? Math.max(1, Math.ceil(result.total / result.page_size))
    : 1
  const open = filters.voucher !== undefined || filters.entry !== undefined
  const [headerDirty, setHeaderDirty] = React.useState(false)
  const [activeLineId, setActiveLineId] = React.useState<string | null>(null)

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
          <h2 className="font-display text-base font-medium">
            Couldn’t load your entries
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            The request to the web API failed. Check that it is running and
            reachable, then reload.
          </p>
        </Card>
      ) : loading ? (
        <LoadingState />
      ) : !result || result.items.length === 0 ? (
        <EmptyState filters={filters} onClear={onClearFilters} />
      ) : (
        <>
          <VoucherTable
            groups={result.items}
            onSelectEntry={(key) => {
              setActiveLineId(key.line ?? null)
              onSelectEntry(key)
            }}
          />
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {result.total} voucher{result.total === 1 ? '' : 's'}
            </p>
            <Pagination
              page={result.page}
              pageCount={pageCount}
              onPageChange={onPageChange}
            />
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
        initialLineId={activeLineId}
        onOpenChange={(next) => {
          if (!next) {
            onSelectEntry({})
            setHeaderDirty(false)
            setActiveLineId(null)
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
