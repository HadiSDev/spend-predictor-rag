import * as React from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { EntriesPanel } from '#/components/entries/entries-panel'
import { canManageCompanies, useApi, usePrincipal } from '#/lib/auth'
import { companiesQueryOptions } from '#/lib/companies'
import {
  voucherAuditQueryOptions,
  voucherDetailQueryOptions,
  voucherGroupsQueryOptions,
} from '#/lib/entries'
import type { VoucherKey } from '#/lib/entries'
import {
  createInvoiceLineMutation,
  deleteInvoiceLineMutation,
  reprocessInvoiceMutation,
  updateInvoiceLineMutation,
  updateInvoiceMutation,
  verifyInvoiceLineMutation,
  verifyInvoiceMutation,
} from '#/lib/invoices'
import { entriesSummaryOptions } from '#/lib/reports'
import { spendTreeQueryOptions } from '#/lib/spend-trees'
import {
  applyFilterChange,
  applyVoucherSelection,
  listableEntryTypes,
  validateEntrySearch,
} from '#/lib/entry-search'
import { vendorsQueryOptions } from '#/lib/vendors'

export const Route = createFileRoute('/_authed/entries')({
  component: EntriesPage,
  // The label, not the path: `/entries` is what every shared voucher link
  // carries, and the panel's whole design rests on those links resolving.
  staticData: { title: 'Spend Lines' },
  validateSearch: validateEntrySearch,
})

function EntriesPage() {
  const api = useApi()
  const principal = usePrincipal()
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

  // The open voucher's company decides which taxonomy its lines are corrected
  // against. Resolved here rather than in the editor so one request serves
  // every line in the panel — a voucher can carry a dozen.
  const openCompanyId = voucherDetail.data?.invoice?.company_id ?? null
  const openCompany = companies.data?.find((c) => c.id === openCompanyId)
  const spendTree = useQuery(spendTreeQueryOptions(api, openCompany?.spend_tree_id ?? null))
  // `null` means "still loading", `[]` means "this company has no tree" — the
  // editor says something different for each, and collapsing them would show a
  // settings gap as a spinner that never resolves.
  const spendTreeNodes = openCompany
    ? openCompany.spend_tree_id === null
      ? []
      : (spendTree.data?.nodes ?? null)
    : null

  const verifyLine = useMutation(verifyInvoiceLineMutation(api, queryClient))
  const updateHeader = useMutation(updateInvoiceMutation(api, queryClient))
  const verifyHeader = useMutation(verifyInvoiceMutation(api, queryClient))
  const updateLine = useMutation(updateInvoiceLineMutation(api, queryClient))
  const createLine = useMutation(createInvoiceLineMutation(api, queryClient))
  const deleteLine = useMutation(deleteInvoiceLineMutation(api, queryClient))
  const reprocess = useMutation(reprocessInvoiceMutation(api, queryClient))

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
      onSelectEntry={(key) => navigate({ search: applyVoucherSelection(filters, key) })}
      onVerifyLine={async (lineId, corrections) => {
        await verifyLine.mutateAsync({ id: lineId, corrections })
      }}
      spendTreeNodes={spendTreeNodes}
      companySettingsHref={openCompanyId ? `/settings/companies` : undefined}
      onUpdateHeader={async (invoiceId, changes) => {
        await updateHeader.mutateAsync({ id: invoiceId, body: changes })
      }}
      onVerifyHeader={async (invoiceId, changes) => {
        await verifyHeader.mutateAsync({ id: invoiceId, body: changes })
      }}
      onUpdateLine={async (lineId, changes) => {
        await updateLine.mutateAsync({ id: lineId, body: changes })
      }}
      onCreateLine={async (invoiceId) => {
        // Empty: the reviewer fills the row in afterwards. A form to complete
        // first would put a dialog between them and a three-step operation.
        await createLine.mutateAsync({ invoiceId, body: {} })
      }}
      onDeleteLine={async (lineId) => {
        await deleteLine.mutateAsync({ id: lineId })
      }}
      onReprocess={async (invoiceId) => {
        await reprocess.mutateAsync({ id: invoiceId })
      }}
      // The same role the endpoint requires. Offering the action to a viewer
      // would only teach them the screen lies about what they can do.
      canManage={canManageCompanies(principal)}
    />
  )
}
