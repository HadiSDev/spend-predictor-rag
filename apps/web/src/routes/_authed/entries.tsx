import * as React from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { EntriesPanel } from '#/components/entries/entries-panel'
import { canManageCompanies, useApi, usePrincipal } from '#/lib/auth/auth'
import { companiesQueryOptions } from '#/lib/api/companies'
import {
  voucherAuditQueryOptions,
  voucherDetailQueryOptions,
  voucherGroupsQueryOptions,
} from '#/lib/api/entries'
import type { VoucherKey } from '#/lib/api/entries'
import {
  createInvoiceLineMutation,
  deleteInvoiceLineMutation,
  reprocessInvoiceMutation,
  updateInvoiceLineMutation,
  updateInvoiceMutation,
  verifyInvoiceLineMutation,
  verifyInvoiceMutation,
} from '#/lib/api/invoices'
import { entriesSummaryOptions } from '#/lib/api/reports'
import { spendTreeQueryOptions } from '#/lib/api/spend-trees'
import {
  applyFilterChange,
  applyVoucherSelection,
  listableEntryTypes,
  validateEntrySearch,
} from '#/lib/entry-search'
import { vendorsQueryOptions } from '#/lib/api/vendors'

export const Route = createFileRoute('/_authed/entries')({
  component: EntriesPage,
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

  const voucherKey: VoucherKey = {
    voucher: filters.voucher,
    entry: filters.entry,
  }
  const voucherOpen =
    filters.voucher !== undefined || filters.entry !== undefined

  const groups = useQuery(voucherGroupsQueryOptions(api, filters))
  const companies = useQuery(companiesQueryOptions(api))
  const vendors = useQuery(vendorsQueryOptions(api, { q: vendorQuery }))
  const summary = useQuery(entriesSummaryOptions(api))
  const voucherDetail = useQuery(voucherDetailQueryOptions(api, voucherKey))
  const voucherAudit = useQuery(voucherAuditQueryOptions(api, voucherKey))

  const openCompanyId = voucherDetail.data?.invoice?.company_id ?? null
  const openCompany = companies.data?.find((c) => c.id === openCompanyId)
  const spendTree = useQuery(
    spendTreeQueryOptions(api, openCompany?.spend_tree_id ?? null),
  )
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
    () =>
      listableEntryTypes(
        (summary.data?.rows ?? []).map((row) => row.entry_type),
      ),
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
      onFiltersChange={(changes) =>
        navigate({ search: applyFilterChange(filters, changes) })
      }
      onClearFilters={() => navigate({ search: {} })}
      onPageChange={(page) => navigate({ search: { ...filters, page } })}
      onVendorSearch={setVendorQuery}
      voucherDetail={voucherDetail.data}
      voucherLoading={voucherDetail.isPending && voucherOpen}
      auditRows={voucherAudit.data ?? []}
      auditLoading={voucherAudit.isPending && voucherOpen}
      tab={filters.tab ?? 'details'}
      onTabChange={(tab) => navigate({ search: { ...filters, tab } })}
      onSelectEntry={(key) =>
        navigate({ search: applyVoucherSelection(filters, key) })
      }
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
        await createLine.mutateAsync({ invoiceId, body: {} })
      }}
      onDeleteLine={async (lineId) => {
        await deleteLine.mutateAsync({ id: lineId })
      }}
      onReprocess={async (invoiceId) => {
        await reprocess.mutateAsync({ id: invoiceId })
      }}
      canManage={canManageCompanies(principal)}
    />
  )
}
