import { clerkMiddleware } from '@clerk/tanstack-react-start/server'
import { createCsrfMiddleware, createStart } from '@tanstack/react-start'

const csrfMiddleware = createCsrfMiddleware({
  filter: (ctx) => ctx.handlerType === 'serverFn',
})

/** Global request middleware: CSRF protection, then Clerk. */
export const startInstance = createStart(() => {
  return {
    requestMiddleware: [csrfMiddleware, clerkMiddleware()],
  }
})
