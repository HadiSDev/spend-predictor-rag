import { API_BASE_URL } from './env'

/** Returns the current Clerk session token, or null when signed out. */
export type TokenGetter = () => Promise<string | null>

/** Error thrown for any non-2xx web API response. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly body?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** A typed, authenticated client for the web API bound to a token getter. */
export interface ApiClient {
  get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T>
}

function withQuery(path: string, params?: Record<string, string | number | undefined>): string {
  if (!params) return path
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `${path}?${qs}` : path
}

/** Build a client that attaches `Authorization: Bearer <token>` to each request. */
export function createApiClient(getToken: TokenGetter): ApiClient {
  async function request<T>(
    path: string,
    params?: Record<string, string | number | undefined>,
  ): Promise<T> {
    const token = await getToken()
    const res = await fetch(`${API_BASE_URL}${withQuery(path, params)}`, {
      headers: {
        Accept: 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
    if (!res.ok) {
      let body: unknown
      try {
        body = await res.json()
      } catch {
        // non-JSON error body; leave undefined
      }
      throw new ApiError(res.status, `Request to ${path} failed with ${res.status}`, body)
    }
    return (await res.json()) as T
  }

  return { get: request }
}
