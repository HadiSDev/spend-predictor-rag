import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card } from '#/components/ui'
import { AccountsPanel } from '#/components/settings/companies/accounts-panel'
import { canManageCompanies, useApi, usePrincipal } from '#/lib/auth/auth'
import {
  accountsQueryOptions,
  refreshAccountsMutation,
  updateAccountMutation,
} from '#/lib/api/accounts'
import { companiesQueryOptions } from '#/lib/api/companies'
import { integrationsQueryOptions } from '#/lib/api/integrations'

export const Route = createFileRoute(
  '/_authed/settings/companies/$companyId/accounts',
)({
  component: AccountsSection,
  staticData: { title: 'Accounts' },
})

function AccountsSection() {
  const { companyId } = Route.useParams()
  const api = useApi()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canManage = canManageCompanies(usePrincipal())

  const companies = useQuery(
    companiesQueryOptions(api, { includeInactive: true }),
  )
  const integrations = useQuery(integrationsQueryOptions(api))

  const company = companies.data?.find((c) => c.id === companyId)
  const integration = integrations.data?.find((i) => i.company_id === companyId)

  const accounts = useQuery(accountsQueryOptions(api, integration?.id ?? null))
  const update = useMutation(
    updateAccountMutation(api, queryClient, integration?.id ?? ''),
  )
  const refresh = useMutation(
    refreshAccountsMutation(api, queryClient, integration?.id ?? ''),
  )

  if (companies.isError || integrations.isError) {
    return (
      <Card className="p-8 text-center">
        <h2 className="font-display text-base font-medium">
          Couldn’t load this company
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          The request to the web API failed. Check that it is running and
          reachable, then reload.
        </p>
      </Card>
    )
  }

  if (!companies.isPending && company === undefined) {
    return (
      <Card className="p-8 text-center">
        <h2 className="font-display text-base font-medium">
          Company not found
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          It may have been removed, or it belongs to another organization.
        </p>
      </Card>
    )
  }

  return (
    <AccountsPanel
      companyName={company?.name ?? ''}
      accounts={accounts.data ?? []}
      loading={
        companies.isPending || integrations.isPending || accounts.isPending
      }
      canManage={canManage}
      hasIntegration={integration !== undefined}
      onToggle={(id, changes) => update.mutateAsync({ id, body: changes })}
      onRefresh={() => refresh.mutateAsync()}
      onBack={() => navigate({ to: '/settings/companies' })}
    />
  )
}
