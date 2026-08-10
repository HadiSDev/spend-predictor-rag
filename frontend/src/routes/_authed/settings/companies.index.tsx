import * as React from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card } from '#/components/ui'
import { CompaniesPanel } from '#/components/settings/companies-panel'
import { canManageCompanies, useApi, usePrincipal } from '#/lib/auth'
import {
  companiesQueryOptions,
  createCompanyMutation,
  recomputeCompanyFxMutation,
  setCompanyActiveMutation,
  updateCompanyMutation,
} from '#/lib/companies'
import { erpTypesQueryOptions } from '#/lib/erp-types'
import { spendTreesQueryOptions } from '#/lib/spend-trees'
import {
  connectIntegrationMutation,
  integrationsQueryOptions,
  updateIntegrationMutation,
} from '#/lib/integrations'

export const Route = createFileRoute('/_authed/settings/companies/')({
  component: CompaniesSection,
})

function CompaniesSection() {
  const api = useApi()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const principal = usePrincipal()
  const canManage = canManageCompanies(principal)

  const [includeInactive, setIncludeInactive] = React.useState(false)
  const companies = useQuery(companiesQueryOptions(api, { includeInactive }))
  // Only managers ever open the create dialog, so only they need the catalog.
  const erpTypes = useQuery({ ...erpTypesQueryOptions(api), enabled: canManage })
  const integrations = useQuery(integrationsQueryOptions(api))
  const create = useMutation(createCompanyMutation(api, queryClient))
  // The org's trees, so a company's taxonomy is chosen from a list rather than
  // typed. Read-only for any member, so this needs no role gate of its own.
  const spendTrees = useQuery(spendTreesQueryOptions(api))
  const update = useMutation(updateCompanyMutation(api, queryClient))
  const updateIntegration = useMutation(updateIntegrationMutation(api, queryClient))
  const connectIntegration = useMutation(connectIntegrationMutation(api, queryClient))
  const setActive = useMutation(setCompanyActiveMutation(api, queryClient))
  const recomputeFx = useMutation(recomputeCompanyFxMutation(api, queryClient))

  if (companies.isError) {
    return (
      <Card className="p-8 text-center">
        <h2 className="font-display text-base font-medium">Couldn’t load your companies</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          The request to the web API failed. Check that it is running and reachable, then reload.
        </p>
      </Card>
    )
  }

  return (
    <CompaniesPanel
      companies={companies.data ?? []}
      loading={companies.isPending}
      includeInactive={includeInactive}
      onIncludeInactiveChange={setIncludeInactive}
      canManage={canManage}
      erpTypes={erpTypes.data ?? []}
      erpTypesLoading={erpTypes.isPending && canManage}
      integrations={integrations.data ?? []}
      spendTrees={spendTrees.data ?? []}
      onReviewStaleLines={(companyId) =>
        navigate({ to: '/entries', search: { company_id: companyId } })
      }
      onCreate={(values) =>
        create.mutateAsync({
          name: values.name,
          base_currency: values.base_currency,
          // Empty optional fields are sent as null, not "".
          country_code: values.country_code || null,
          vat_number: values.vat_number || null,
          // Empty means "the organization's default tree" — sent as null so
          // the server materializes it, never as "" which resolves to nothing.
          spend_tree_id: values.spend_tree_id || null,
          // The company and its ERP connection go in one request, so a failure
          // cannot leave a company that syncs nothing.
          integration: {
            erp_type: values.erp_type,
            // Blank inputs are omitted so the connector falls back to its own
            // defaults rather than storing empty strings.
            credentials: Object.fromEntries(
              Object.entries(values.credentials).filter(([, value]) => value.trim() !== ''),
            ),
          },
        })
      }
      onUpdate={(id, changes) =>
        update.mutateAsync({
          id,
          body: {
            ...(changes.name !== undefined ? { name: changes.name } : {}),
            ...(changes.country_code !== undefined
              ? { country_code: changes.country_code || null }
              : {}),
            ...(changes.vat_number !== undefined
              ? { vat_number: changes.vat_number || null }
              : {}),
            ...(changes.base_currency !== undefined
              ? { base_currency: changes.base_currency }
              : {}),
            // Empty string means "the organization's default", which the
            // server resolves — so it is sent as null, not dropped.
            ...(changes.spend_tree_id !== undefined
              ? { spend_tree_id: changes.spend_tree_id || null }
              : {}),
          },
        })
      }
      onUpdateIntegration={(id, changes) =>
        updateIntegration.mutateAsync({
          id,
          body: {
            ...(changes.label !== undefined ? { label: changes.label || null } : {}),
            // Present only when replacement was chosen; omitting it leaves the
            // stored secret alone.
            ...(changes.credentials !== undefined ? { credentials: changes.credentials } : {}),
          },
        })
      }
      onConnectIntegration={(companyId, values) =>
        connectIntegration.mutateAsync({
          company_id: companyId,
          erp_type: values.erp_type,
          label: values.label || null,
          credentials: values.credentials,
        })
      }
      onSetActive={(id, active) => setActive.mutateAsync({ id, active })}
      onRecomputeFx={(id) => recomputeFx.mutateAsync({ id })}
      onManageAccounts={(companyId) =>
        navigate({ to: '/settings/companies/$companyId/accounts', params: { companyId } })
      }
    />
  )
}
