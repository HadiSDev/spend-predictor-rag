import { HeadContent, Scripts, createRootRoute } from '@tanstack/react-router'
import { TanStackRouterDevtoolsPanel } from '@tanstack/react-router-devtools'
import { TanStackDevtools } from '@tanstack/react-devtools'
import { ClerkProvider } from '@clerk/tanstack-react-start'

import { ThemeProvider, ToastProvider, TooltipProvider } from '#/components/ui'
import { CLERK_PUBLISHABLE_KEY } from '#/lib/env'
import appCss from '../styles.css?url'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      {
        charSet: 'utf-8',
      },
      {
        name: 'viewport',
        content: 'width=device-width, initial-scale=1',
      },
      {
        title: 'Spend Predictor',
      },
    ],
    links: [
      {
        rel: 'stylesheet',
        href: appCss,
      },
    ],
  }),
  shellComponent: RootDocument,
})

function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <TooltipProvider>
        <ToastProvider>{children}</ToastProvider>
      </TooltipProvider>
    </ThemeProvider>
  )
}

function ConfigError() {
  return (
    <ThemeProvider>
      <div className="grid min-h-screen place-items-center bg-background px-6 text-center">
        <div className="max-w-md">
          <h1 className="font-display text-lg font-semibold">Configuration required</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            <code>VITE_CLERK_PUBLISHABLE_KEY</code> is not set. Copy{' '}
            <code>apps/web/.env.example</code> to <code>.env</code> and set your Clerk
            publishable key, then restart the dev server.
          </p>
        </div>
      </div>
    </ThemeProvider>
  )
}

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {CLERK_PUBLISHABLE_KEY ? (
          <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
            <AppProviders>{children}</AppProviders>
          </ClerkProvider>
        ) : (
          <ConfigError />
        )}
        <TanStackDevtools
          config={{
            position: 'bottom-right',
          }}
          plugins={[
            {
              name: 'Tanstack Router',
              render: <TanStackRouterDevtoolsPanel />,
            },
          ]}
        />
        <Scripts />
      </body>
    </html>
  )
}
