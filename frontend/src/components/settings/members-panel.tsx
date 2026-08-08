import * as React from 'react'
import { useOrganization, useUser } from '@clerk/tanstack-react-start'
import { useQueryClient } from '@tanstack/react-query'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '#/components/ui'
import { clerkErrorCode, serverErrorMessage } from '#/lib/form-errors'
import { meKey } from '#/lib/organization'
import { ReadOnlyNotice, SettingsCard } from './form'
import { initials } from './profile-panel'

export interface MemberRow {
  /** Clerk membership id — what role changes and removals address. */
  id: string
  name: string
  email: string
  imageUrl?: string
  role: string
  isSelf: boolean
}

export interface InvitationRow {
  id: string
  email: string
  role: string
  status: string
}

export interface RoleOption {
  value: string
  label: string
}

/** Clerk role keys are namespaced (`org:admin`); the API stores the bare name. */
export function isAdminRole(role: string): boolean {
  return role === 'admin' || role.endsWith(':admin')
}

export function roleLabel(role: string, roles: Array<RoleOption>): string {
  return roles.find((option) => option.value === role)?.label ?? role.replace(/^org:/, '')
}

/** Clerk reports invitation status as a raw lowercase token. */
export function humanizeStatus(status: string): string {
  const text = status.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function statusVariant(status: string): 'success' | 'warning' | 'default' {
  if (status === 'accepted') return 'success'
  if (status === 'pending') return 'warning'
  return 'default'
}

export interface MembersViewProps {
  members: Array<MemberRow>
  invitations: Array<InvitationRow>
  /** Roles the Clerk instance allows — never a hard-coded list. */
  roles: Array<RoleOption>
  canManage: boolean
  loading?: boolean
  hasMore?: boolean
  onLoadMore?: () => void
  onChangeRole: (membershipId: string, role: string) => Promise<unknown>
  onRemove: (membershipId: string) => Promise<unknown>
  onInvite: (email: string, role: string) => Promise<unknown>
  onRevokeInvitation: (invitationId: string) => Promise<unknown>
}

/**
 * Why a member's row offers no controls, or null when it does. Keeping the
 * organization administrable matters more than a uniform UI, so the reason is
 * always shown rather than the control silently disappearing.
 */
export function blockedReason(member: MemberRow, members: Array<MemberRow>): string | null {
  if (member.isSelf) return 'You can’t change your own role.'
  const admins = members.filter((row) => isAdminRole(row.role))
  if (isAdminRole(member.role) && admins.length <= 1) {
    return 'The only admin — promote someone else first.'
  }
  return null
}

/**
 * Clerk enables organization email invitations per instance, and there is no
 * dashboard setting for it — its own message just says "contact support", which
 * leaves the admin with nowhere to go. Say what to actually do instead.
 */
export function inviteErrorMessage(error: unknown): string {
  if (clerkErrorCode(error) === 'invitations_not_supported_in_organization') {
    return 'Email invitations aren’t enabled for this Clerk instance. Ask Clerk support to enable them; until then, add people from the Clerk dashboard and they will appear here.'
  }
  return serverErrorMessage(error)
}

export function MembersView({
  members,
  invitations,
  roles,
  canManage,
  loading = false,
  hasMore = false,
  onLoadMore,
  onChangeRole,
  onRemove,
  onInvite,
  onRevokeInvitation,
}: MembersViewProps) {
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [inviteEmail, setInviteEmail] = React.useState('')
  const [inviteRole, setInviteRole] = React.useState<string | null>(null)
  const [inviteError, setInviteError] = React.useState<string | null>(null)
  const [confirmRemoval, setConfirmRemoval] = React.useState<string | null>(null)

  const defaultRole = roles.at(-1)?.value ?? ''
  const selectedInviteRole = inviteRole ?? defaultRole

  async function run(
    action: () => Promise<unknown>,
    onError: (message: string) => void,
    format: (error: unknown) => string = serverErrorMessage,
  ) {
    setBusy(true)
    onError('')
    try {
      await action()
    } catch (failure) {
      onError(format(failure))
    } finally {
      setBusy(false)
    }
  }

  function handleInvite(event: React.FormEvent) {
    event.preventDefault()
    const email = inviteEmail.trim()
    if (!email) return
    void run(
      async () => {
        await onInvite(email, selectedInviteRole)
        setInviteEmail('')
      },
      (message) => setInviteError(message || null),
      inviteErrorMessage,
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <SettingsCard
        title="Members"
        description="Membership and roles are managed in Clerk, which is authoritative for who belongs to this organization."
      >
        <div className="flex flex-col gap-4">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading members…</p>
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {members.map((member) => {
                const blocked = blockedReason(member, members)
                return (
                  <li key={member.id} className="flex flex-wrap items-center gap-3 py-3">
                    <Avatar className="size-9">
                      {member.imageUrl ? (
                        <AvatarImage src={member.imageUrl} alt={member.name} />
                      ) : null}
                      <AvatarFallback>{initials(member.name || member.email)}</AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">
                        {member.name || member.email}
                        {member.isSelf ? (
                          <span className="ml-2 text-xs text-muted-foreground">You</span>
                        ) : null}
                      </div>
                      <div className="truncate text-xs text-muted-foreground">{member.email}</div>
                    </div>

                    {canManage && !blocked ? (
                      <Select
                        // On the root, `items` drives typeahead and value
                        // serialization; the trigger's label comes from the
                        // matching prop on SelectValue below.
                        items={roles}
                        value={member.role}
                        onValueChange={(value) =>
                          void run(
                            () => onChangeRole(member.id, String(value)),
                            (message) => setError(message || null),
                          )
                        }
                        disabled={busy}
                      >
                        <SelectTrigger className="h-9 w-40" aria-label={`Role for ${member.email}`}>
                          <SelectValue items={roles} />
                        </SelectTrigger>
                        <SelectContent>
                          {roles.map((role) => (
                            <SelectItem key={role.value} value={role.value}>
                              {role.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <Badge variant="outline">{roleLabel(member.role, roles)}</Badge>
                    )}

                    {canManage ? (
                      blocked ? (
                        <span className="text-xs text-muted-foreground">{blocked}</span>
                      ) : confirmRemoval === member.id ? (
                        <span className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={busy}
                            onClick={() =>
                              void run(
                                async () => {
                                  await onRemove(member.id)
                                  setConfirmRemoval(null)
                                },
                                (message) => setError(message || null),
                              )
                            }
                          >
                            Confirm
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setConfirmRemoval(null)}>
                            Cancel
                          </Button>
                        </span>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy}
                          onClick={() => setConfirmRemoval(member.id)}
                        >
                          Remove
                        </Button>
                      )
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}

          {hasMore ? (
            <div>
              <Button size="sm" variant="secondary" disabled={busy} onClick={onLoadMore}>
                Load more
              </Button>
            </div>
          ) : null}

          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          {!canManage ? (
            <ReadOnlyNotice>
              Only an organization admin can invite people or change roles.
            </ReadOnlyNotice>
          ) : null}
        </div>
      </SettingsCard>

      {canManage ? (
        <SettingsCard
          title="Invitations"
          description="Invited people join with the role you choose."
        >
          <div className="flex flex-col gap-4">
            <form className="flex flex-wrap items-end gap-2" onSubmit={handleInvite}>
              <Input
                aria-label="Invite email address"
                type="email"
                placeholder="colleague@company.com"
                className="max-w-72"
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
              />
              <Select
                items={roles}
                value={selectedInviteRole}
                onValueChange={(value) => setInviteRole(String(value))}
              >
                <SelectTrigger className="w-40" aria-label="Invite role">
                  <SelectValue items={roles} />
                </SelectTrigger>
                <SelectContent>
                  {roles.map((role) => (
                    <SelectItem key={role.value} value={role.value}>
                      {role.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button type="submit" disabled={busy || !inviteEmail.trim()}>
                {busy ? 'Inviting…' : 'Send invitation'}
              </Button>
            </form>

            {inviteError ? <p className="text-sm text-destructive">{inviteError}</p> : null}

            {invitations.length > 0 ? (
              <div className="flex flex-col gap-2">
                <h3 className="text-sm font-medium text-foreground">Pending invitations</h3>
                <ul className="flex flex-col divide-y divide-border rounded-xl border border-border">
                {invitations.map((invitation) => (
                  <li key={invitation.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
                    {/* The address and its metadata read as one unit; only the
                        action is pushed to the far edge. */}
                    <span className="min-w-0 truncate text-sm">{invitation.email}</span>
                    <Badge variant="outline">{roleLabel(invitation.role, roles)}</Badge>
                    <Badge variant={statusVariant(invitation.status)}>
                      {humanizeStatus(invitation.status)}
                    </Badge>
                    <span className="ml-auto" />
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() =>
                        void run(
                          () => onRevokeInvitation(invitation.id),
                          (message) => setInviteError(message || null),
                        )
                      }
                    >
                      Revoke
                    </Button>
                  </li>
                ))}
                </ul>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No pending invitations.</p>
            )}
          </div>
        </SettingsCard>
      ) : null}
    </div>
  )
}

/** Fallback when the instance's role list can't be read. */
const FALLBACK_ROLES: Array<RoleOption> = [
  { value: 'org:admin', label: 'Admin' },
  { value: 'org:member', label: 'Member' },
]

/**
 * Binds the view to Clerk's organization APIs. Membership is read from and
 * written to Clerk only — the local `User` rows are a webhook-maintained
 * projection, so a person invited but not yet signed in has no row to read.
 */
export function MembersPanel({ canManage }: { canManage: boolean }) {
  const { user } = useUser()
  const queryClient = useQueryClient()
  const { organization, memberships, invitations, isLoaded } = useOrganization({
    memberships: { pageSize: 20, keepPreviousData: true },
    invitations: { pageSize: 20, keepPreviousData: true },
  })
  const [roles, setRoles] = React.useState<Array<RoleOption>>(FALLBACK_ROLES)

  React.useEffect(() => {
    if (!organization) return
    let cancelled = false
    void organization
      .getRoles({ pageSize: 20 })
      .then((page) => {
        if (cancelled || page.data.length === 0) return
        setRoles(page.data.map((role) => ({ value: role.key, label: role.name })))
      })
      // An instance that doesn't expose roles keeps the fallback.
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [organization])

  /** Re-read the principal: the caller's own role may have just changed. */
  async function refreshPrincipal() {
    await queryClient.invalidateQueries({ queryKey: meKey })
  }

  const members: Array<MemberRow> = (memberships?.data ?? []).map((membership) => {
    const data = membership.publicUserData
    const name = [data?.firstName, data?.lastName].filter(Boolean).join(' ')
    return {
      id: membership.id,
      name: name || data?.identifier || '',
      email: data?.identifier ?? '',
      imageUrl: data?.hasImage ? data.imageUrl : undefined,
      role: membership.role,
      isSelf: !!user && data?.userId === user.id,
    }
  })

  const pending: Array<InvitationRow> = (invitations?.data ?? []).map((invitation) => ({
    id: invitation.id,
    email: invitation.emailAddress,
    role: invitation.role,
    status: invitation.status,
  }))

  return (
    <MembersView
      members={members}
      invitations={pending}
      roles={roles}
      canManage={canManage}
      loading={!isLoaded}
      hasMore={memberships?.hasNextPage ?? false}
      onLoadMore={() => memberships?.fetchNext?.()}
      onChangeRole={async (membershipId, role) => {
        const membership = memberships?.data?.find((entry) => entry.id === membershipId)
        await membership?.update({ role })
        await memberships?.revalidate?.()
        await refreshPrincipal()
      }}
      onRemove={async (membershipId) => {
        const membership = memberships?.data?.find((entry) => entry.id === membershipId)
        await membership?.destroy()
        await memberships?.revalidate?.()
        await refreshPrincipal()
      }}
      onInvite={async (email, role) => {
        await organization?.inviteMember({ emailAddress: email, role })
        await invitations?.revalidate?.()
      }}
      onRevokeInvitation={async (invitationId) => {
        const invitation = invitations?.data?.find((entry) => entry.id === invitationId)
        await invitation?.revoke()
        await invitations?.revalidate?.()
      }}
    />
  )
}
