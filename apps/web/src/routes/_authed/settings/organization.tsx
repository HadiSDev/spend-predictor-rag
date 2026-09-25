import { createFileRoute } from '@tanstack/react-router'
import { useOrganization } from '@clerk/tanstack-react-start'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, Skeleton } from '#/components/ui'
import { DangerZone } from '#/components/settings/organization/danger-zone'
import { MembersPanel } from '#/components/settings/organization/members-panel'
import { OrganizationPanel } from '#/components/settings/organization/organization-panel'
import { canManageOrganization, useApi, usePrincipal } from '#/lib/auth/auth'
import {
  organizationQueryOptions,
  suspendOrganizationMutation,
  updateOrganizationMutation,
} from '#/lib/api/organization'

export const Route = createFileRoute('/_authed/settings/organization')({
  component: OrganizationSection,
})

function OrganizationSection() {
  const api = useApi()
  const queryClient = useQueryClient()
  const principal = usePrincipal()
  const canManage = canManageOrganization(principal)

  const organization = useQuery(organizationQueryOptions(api))
  const update = useMutation(updateOrganizationMutation(api, queryClient))
  const suspend = useMutation(suspendOrganizationMutation(api, queryClient))
  const clerkOrg = useOrganization()

  if (organization.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-64 rounded-card" />
        <Skeleton className="h-64 rounded-card" />
      </div>
    )
  }

  if (organization.isError) {
    return (
      <Card className="p-8 text-center">
        <h2 className="font-display text-base font-medium">
          Couldn’t load your organization
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          The request to the web API failed. Check that it is running and
          reachable, then reload.
        </p>
      </Card>
    )
  }

  const logo = clerkOrg.organization
  const canUploadLogo = canManage && !!logo

  return (
    <div className="flex flex-col gap-6">
      <OrganizationPanel
        organization={organization.data}
        readOnly={!canManage}
        onSave={(values) => update.mutateAsync(values)}
        logoUrl={logo?.hasImage ? logo.imageUrl : undefined}
        onUploadLogo={
          canUploadLogo
            ? async (file) => void (await logo.setLogo({ file }))
            : undefined
        }
      />

      <MembersPanel canManage={canManage} />

      <DangerZone
        organizationName={organization.data.name}
        canManage={canManage}
        onSuspend={() => suspend.mutateAsync()}
      />
    </div>
  )
}
