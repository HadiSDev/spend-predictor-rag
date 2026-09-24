import { useAuth } from '@clerk/tanstack-react-start'
import { useNavigate } from '@tanstack/react-router'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxIcon,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxTrigger,
  Skeleton,
  useToast,
} from '#/components/ui'
import { useOrgMemberships } from '#/lib/orgs'
import type { OrgMembership } from '#/lib/orgs'

/**
 * Switches the active organization. Clerk's active organization *is* the tenant
 * — the web API scopes every request to the `orgId` claim in the session token —
 * so activating another membership re-scopes the whole app. Discarding the
 * previous tenant's cached data is handled once, centrally, by `OrgScope` in
 * `lib/auth.tsx`.
 *
 * With a single membership there is nothing to switch to, so it renders the
 * organization name as a plain label.
 */
export function OrgSwitcher() {
  const { orgId } = useAuth()
  const { isLoaded, memberships, setActive } = useOrgMemberships()
  const toast = useToast()
  const navigate = useNavigate()

  // `undefined` only while Clerk's active org is not (yet) among the listed
  // memberships; the authed layout guarantees an active org in practice.
  const active = memberships.find((m) => m.id === orgId)

  async function handleChange(next: OrgMembership | null) {
    if (!next || !setActive || next.id === orgId) return
    try {
      await setActive({ organization: next.id })
      // A deep link is meaningless in another tenant — start from the dashboard.
      await navigate({ to: '/' })
    } catch {
      toast.add({
        title: 'Couldn’t switch organization',
        description: 'Please try again.',
      })
    }
  }

  if (!isLoaded) {
    return <Skeleton className="h-4 w-28" data-testid="org-switcher-loading" />
  }

  if (memberships.length <= 1) {
    const name = active?.name ?? memberships.at(0)?.name
    // Nothing to switch to: read as a second line under the lockup, flush with
    // its left edge (the wordmark's offset inside the lockup scales with its
    // width, so an indent matched to it would drift).
    return (
      <span className="truncate text-xs text-muted-foreground" title={name}>
        {name ?? 'No organization'}
      </span>
    )
  }

  return (
    <Combobox
      items={memberships}
      value={active}
      onValueChange={handleChange}
      itemToStringLabel={(m: OrgMembership) => m.name}
      isItemEqualToValue={(a: OrgMembership, b: OrgMembership) => a.id === b.id}
    >
      <ComboboxTrigger
        aria-label="Switch organization"
        className="h-9 border-transparent bg-transparent px-2 hover:bg-muted"
      >
        <span className="truncate text-sm font-medium">
          {active?.name ?? 'Select organization'}
        </span>
        <ComboboxIcon />
      </ComboboxTrigger>
      <ComboboxContent className="w-64">
        <div className="p-1">
          {/* No chevron: this input sits inside the open popup, so there is
              nothing left for it to open. */}
          <ComboboxInput
            placeholder="Search organizations…"
            aria-label="Search organizations"
            hideIcon
          />
        </div>
        <ComboboxEmpty>No organizations found.</ComboboxEmpty>
        <ComboboxList>
          {(membership: OrgMembership) => (
            <ComboboxItem key={membership.id} value={membership}>
              {membership.name}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
