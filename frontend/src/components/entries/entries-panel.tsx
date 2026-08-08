import { Button, Card, Pagination, Skeleton } from '#/components/ui'
import { FilterBar } from './filter-bar'
import { VoucherTable } from './voucher-table'
import { EntryDrawer } from './entry-drawer'
import type {
  CompanyRead,
  EntryFilters,
  ErpEntryRead,
  Page,
  VendorRead,
  VoucherGroupRead,
} from '#/lib/types'

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
  /** The posting whose detail is open, and its loading state. */
  selectedEntry: ErpEntryRead | undefined
  selectedEntryLoading: boolean
  selectedEntryId: string | null
  onSelectEntry: (id: string | null) => void
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
  selectedEntry,
  selectedEntryLoading,
  selectedEntryId,
  onSelectEntry,
}: EntriesPanelProps) {
  const pageCount = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1

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

      <EntryDrawer
        entry={selectedEntry}
        loading={selectedEntryLoading}
        open={selectedEntryId !== null}
        onOpenChange={(open) => {
          if (!open) onSelectEntry(null)
        }}
      />
    </div>
  )
}
