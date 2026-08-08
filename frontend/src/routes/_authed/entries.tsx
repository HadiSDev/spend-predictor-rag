import * as React from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { EntriesPanel } from '#/components/entries/entries-panel'
import { useApi } from '#/lib/auth'
import { companiesQueryOptions } from '#/lib/companies'
import { entryQueryOptions, voucherGroupsQueryOptions } from '#/lib/entries'
import { entriesSummaryOptions } from '#/lib/reports'
import { applyFilterChange, listableEntryTypes, validateEntrySearch } from '#/lib/entry-search'
import { vendorsQueryOptions } from '#/lib/vendors'

export const Route = createFileRoute('/_authed/entries')({
  component: EntriesPage,
  staticData: { title: 'Entries' },
  validateSearch: validateEntrySearch,
})

function EntriesPage() {
  const api = useApi()
  const navigate = useNavigate({ from: Route.fullPath })
  const filters = Route.useSearch()

  const [vendorQuery, setVendorQuery] = React.useState('')
  const [selectedEntryId, setSelectedEntryId] = React.useState<string | null>(null)

  const groups = useQuery(voucherGroupsQueryOptions(api, filters))
  const companies = useQuery(companiesQueryOptions(api))
  const vendors = useQuery(vendorsQueryOptions(api, { q: vendorQuery }))
  // The entry-type options come from the summary report rather than a
  // hardcoded enum: connectors are free to emit their own types, and this way
  // the list only offers what the org actually has. The summary reports over
  // every entry, though, so the types no listing returns are dropped.
  const summary = useQuery(entriesSummaryOptions(api))
  const entry = useQuery(entryQueryOptions(api, selectedEntryId))

  const entryTypes = React.useMemo(
    () => listableEntryTypes((summary.data?.rows ?? []).map((row) => row.entry_type)),
    [summary.data],
  )

  return (
    <EntriesPanel
      result={groups.data}
      loading={groups.isPending}
      error={groups.isError}
      filters={filters}
      companies={companies.data ?? []}
      vendors={vendors.data?.items ?? []}
      entryTypes={entryTypes}
      onFiltersChange={(changes) => navigate({ search: applyFilterChange(filters, changes) })}
      onClearFilters={() => navigate({ search: {} })}
      onPageChange={(page) => navigate({ search: { ...filters, page } })}
      onVendorSearch={setVendorQuery}
      selectedEntry={entry.data}
      selectedEntryLoading={entry.isPending && selectedEntryId !== null}
      selectedEntryId={selectedEntryId}
      onSelectEntry={setSelectedEntryId}
    />
  )
}
