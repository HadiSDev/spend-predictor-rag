/** Typed access to the Vite-exposed environment. */

/** Base URL of the web API (no trailing slash). */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
    /\/$/,
    '',
  ) ?? 'http://localhost:8100'

/** Clerk publishable key. */
export const CLERK_PUBLISHABLE_KEY = import.meta.env
  .VITE_CLERK_PUBLISHABLE_KEY as string | undefined

/** Whether to offer Google OAuth on the sign-in page. */
export const GOOGLE_OAUTH_ENABLED =
  (import.meta.env.VITE_CLERK_GOOGLE_OAUTH as string | undefined) === 'true'

/** Throws a readable error when required config is missing. */
export function assertRequiredEnv(): void {
  if (!CLERK_PUBLISHABLE_KEY) {
    throw new Error(
      'Missing VITE_CLERK_PUBLISHABLE_KEY. Copy apps/web/.env.example to .env and set it ' +
        'to your Clerk publishable key.',
    )
  }
}
