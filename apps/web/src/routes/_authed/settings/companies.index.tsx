import * as React from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card } from '#/components/ui'
import { CompaniesPanel } from '#/components/settings/companies/companies-panel'
import { canManageCompanies, useApi, usePrincipal } from '#/lib/auth/auth'
import {
  companiesQueryOptions,
  createCompanyMutation,
  recategorizeCompanyMutation,
  recomputeCompanyFxMutation,
  deleteCompanyMutation,
  setCompanyActiveMutation,
  updateCompanyMutation,
} from '#/lib/api/companies'
import { erpTypesQueryOptions } from '#/lib/api/erp-types'
import { spendTreesQueryOptions } from '#/lib/api/spend-trees'
import {
  connectIntegrationMutation,
  integrationsQueryOptions,
  replaceIntegrationMutation,
  updateIntegrationMutation,
} from '#/lib/api/integrations'

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
  const erpTypes = useQuery({
    ...erpTypesQueryOptions(api),
    enabled: canManage,
  })
  const integrations = useQuery(integrationsQueryOptions(api))
  const create = useMutation(createCompanyMutation(api, queryClient))
  const spendTrees = useQuery(spendTreesQueryOptions(api))
  const update = useMutation(updateCompanyMutation(api, queryClient))
  const updateIntegration = useMutation(
    updateIntegrationMutation(api, queryClient),
  )
  const replaceIntegration = useMutation(
    replaceIntegrationMutation(api, queryClient),
  )
  const connectIntegration = useMutation(
    connectIntegrationMutation(api, queryClient),
  )
  const setActive = useMutation(setCompanyActiveMutation(api, queryClient))
  const removeCompany = useMutation(deleteCompanyMutation(api, queryClient))
  const recomputeFx = useMutation(recomputeCompanyFxMutation(api, queryClient))
  const recategorize = useMutation(
    recategorizeCompanyMutation(api, queryClient),
  )

  if (companies.isError) {
    return (
      <Card className="p-8 text-center">
        <h2 className="font-display text-base font-medium">
          Couldn’t load your companies
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          The request to the web API failed. Check that it is running and
          reachable, then reload.
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
      canDelete={principal.isSystemAdmin}
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
          country_code: values.country_code || null,
          vat_number: values.vat_number || null,
          spend_tree_id: values.spend_tree_id || null,
          integration: {
            erp_type: values.erp_type,
            credentials: Object.fromEntries(
              Object.entries(values.credentials).filter(
                ([, value]) => value.trim() !== '',
              ),
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
            ...(changes.label !== undefined
              ? { label: changes.label || null }
              : {}),
            ...(changes.credentials !== undefined
              ? { credentials: changes.credentials }
              : {}),
          },
        })
      }
      onReplaceIntegration={(id, values) =>
        replaceIntegration.mutateAsync({
          id,
          body: {
            erp_type: values.erp_type,
            label: values.label || null,
            credentials: values.credentials,
            ...(values.confirm ? { confirm: true } : {}),
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
      onDelete={(id, confirm) => removeCompany.mutateAsync({ id, confirm })}
      onRecomputeFx={(id) => recomputeFx.mutateAsync({ id })}
      onRecategorize={(id) => recategorize.mutateAsync({ id })}
      onManageAccounts={(companyId) =>
        navigate({
          to: '/settings/companies/$companyId/accounts',
          params: { companyId },
        })
      }
    />
  )
}
