import { createFileRoute, redirect } from '@tanstack/react-router'

/** `/settings` has no content of its own — Profile is the default section. */
export const Route = createFileRoute('/_authed/settings/')({
  beforeLoad: () => {
    throw redirect({ to: '/settings/profile' })
  },
})
