import { createFileRoute } from '@tanstack/react-router'
import { AuthenticateWithRedirectCallback } from '@clerk/tanstack-react-start'

export const Route = createFileRoute('/sso-callback')({ component: SsoCallback })

/** Completes an OAuth redirect flow, then Clerk routes to the completion URL. */
function SsoCallback() {
  return (
    <div className="grid min-h-screen place-items-center bg-background text-muted-foreground">
      <AuthenticateWithRedirectCallback signInForceRedirectUrl="/" signUpForceRedirectUrl="/" />
      Finishing sign-in…
    </div>
  )
}
