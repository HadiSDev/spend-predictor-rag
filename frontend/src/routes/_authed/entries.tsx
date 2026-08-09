import * as React from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { EntriesPanel } from '#/components/entries/entries-panel'
import { useApi } from '#/lib/auth'
import { companiesQueryOptions } from '#/lib/companies'
import {
  voucherAuditQueryOptions,
  voucherDetailQueryOptions,
  voucherGroupsQueryOptions,
} from '#/lib/entries'
import type { VoucherKey } from '#/lib/entries'
import { updateInvoiceMutation, verifyInvoiceLineMutation } from '#/lib/invoices'
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
  const queryClient = useQueryClient()
  const filters = Route.useSearch()

  const [vendorQuery, setVendorQuery] = React.useState('')

  // The open voucher, addressed by whichever of the two the URL carries — a
  // voucherless group has no id of its own, so it is reached by its lone
  // posting's entry id instead (see `voucherPath` in `lib/entries.ts`).
  const voucherKey: VoucherKey = { voucher: filters.voucher, entry: filters.entry }
  const voucherOpen = filters.voucher !== undefined || filters.entry !== undefined

  const groups = useQuery(voucherGroupsQueryOptions(api, filters))
  const companies = useQuery(companiesQueryOptions(api))
  const vendors = useQuery(vendorsQueryOptions(api, { q: vendorQuery }))
  // The entry-type options come from the summary report rather than a
  // hardcoded enum: connectors are free to emit their own types, and this way
  // the list only offers what the org actually has. The summary reports over
  // every entry, though, so the types no listing returns are dropped.
  const summary = useQuery(entriesSummaryOptions(api))
  const voucherDetail = useQuery(voucherDetailQueryOptions(api, voucherKey))
  const voucherAudit = useQuery(voucherAuditQueryOptions(api, voucherKey))

  const verifyLine = useMutation(verifyInvoiceLineMutation(api, queryClient))
  const updateHeader = useMutation(updateInvoiceMutation(api, queryClient))

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
      voucherDetail={voucherDetail.data}
      voucherLoading={voucherDetail.isPending && voucherOpen}
      auditRows={voucherAudit.data ?? []}
      auditLoading={voucherAudit.isPending && voucherOpen}
      tab={filters.tab ?? 'details'}
      onTabChange={(tab) => navigate({ search: { ...filters, tab } })}
      onSelectEntry={(key) => navigate({ search: { ...filters, voucher: key.voucher, entry: key.entry } })}
      onVerifyLine={async (lineId, corrections) => {
        await verifyLine.mutateAsync({ id: lineId, corrections })
      }}
      onUpdateHeader={async (invoiceId, changes) => {
        await updateHeader.mutateAsync({ id: invoiceId, body: changes })
      }}
    />
  )
}
