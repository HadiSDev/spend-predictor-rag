import { Outlet, createFileRoute, redirect } from '@tanstack/react-router'
import { createServerFn } from '@tanstack/react-start'
import { auth } from '@clerk/tanstack-react-start/server'
import { AuthProvider } from '#/lib/auth'

/** Server-side Clerk session check; redirects signed-out users to sign-in. */
const fetchAuthState = createServerFn().handler(async () => {
  const authObject = await auth()
  // TEMP debug: prints in the dev/server terminal (not the browser console).
  console.log('[_authed guard] auth() =>', {
    isAuthenticated: authObject.isAuthenticated,
    userId: authObject.userId,
    sessionId: authObject.sessionId,
    debug: typeof authObject.debug === 'function' ? authObject.debug() : undefined,
  })
  if (!authObject.isAuthenticated) {
    throw redirect({ to: '/sign-in' })
  }
  return { userId: authObject.userId }
})

export const Route = createFileRoute('/_authed')({
  beforeLoad: () => fetchAuthState(),
  component: AuthedLayout,
})

function AuthedLayout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  )
}
