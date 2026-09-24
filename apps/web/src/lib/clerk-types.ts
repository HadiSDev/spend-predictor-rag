/**
 * Clerk resource types, derived from the hooks rather than imported from
 * `@clerk/types` — that package is only a transitive dependency, so importing
 * it directly would not resolve under pnpm's strict layout.
 */
import type { useOrganization, useUser } from '@clerk/tanstack-react-start'

/** The signed-in user (`useUser().user`, past its loading state). */
export type ClerkUser = NonNullable<ReturnType<typeof useUser>['user']>

/** One of the user's email addresses. */
export type ClerkEmailAddress = ClerkUser['emailAddresses'][number]

/** One of the user's connected OAuth accounts. */
export type ClerkExternalAccount = ClerkUser['externalAccounts'][number]

/** The active organization (`useOrganization().organization`). */
export type ClerkOrganization = NonNullable<ReturnType<typeof useOrganization>['organization']>
