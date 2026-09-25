import { createFileRoute, redirect } from '@tanstack/react-router'

/** Redirects `/settings` to Profile. */
export const Route = createFileRoute('/_authed/settings/')({
  beforeLoad: () => {
    throw redirect({ to: '/settings/profile' })
  },
})
