import { API_BASE_URL } from '#/lib/env'

/** Options a caller can pass through to the token getter. */
export interface TokenGetterOptions {
  /** Bypass any cache and mint a freshly-signed token. */
  skipCache?: boolean
}

/** Returns the current Clerk session token, or null when signed out. */
export type TokenGetter = (
  options?: TokenGetterOptions,
) => Promise<string | null>

/** Query-string values accepted by the client. `undefined` keys are dropped. */
export type QueryParams = Record<string, string | number | boolean | undefined>

/** One entry of FastAPI's 422 `detail` array. */
interface ValidationDetail {
  msg?: string
  loc?: Array<string | number>
}

function isValidationDetail(value: unknown): value is ValidationDetail {
  return typeof value === 'object' && value !== null && 'msg' in value
}

/** Format `{msg, loc}` as `field: message`, falling back to the bare message. */
function formatValidationDetail(entry: ValidationDetail): string {
  const msg = entry.msg ?? ''
  const field = entry.loc?.at(-1)
  return field !== undefined && field !== 'body' ? `${field}: ${msg}` : msg
}

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

  /** The API's own explanation, for display. */
  get detail(): string {
    const body = this.body
    if (typeof body !== 'object' || body === null || !('detail' in body)) {
      return this.message
    }
    const { detail } = body
    if (typeof detail === 'string' && detail) {
      return detail
    }
    if (Array.isArray(detail)) {
      const messages = detail
        .filter(isValidationDetail)
        .map(formatValidationDetail)
        .filter(Boolean)
      if (messages.length > 0) {
        return messages.join('; ')
      }
    }
    return this.message
  }
}

/** A typed, authenticated client for the web API bound to a token getter. */
export interface ApiClient {
  get: <T>(path: string, params?: QueryParams) => Promise<T>
  post: <T>(path: string, body?: unknown, params?: QueryParams) => Promise<T>
  patch: <T>(path: string, body?: unknown, params?: QueryParams) => Promise<T>
  del: <T>(path: string, params?: QueryParams) => Promise<T>
  /** Fetch a binary response. */
  getBlob: (path: string, params?: QueryParams) => Promise<Blob>
}

function withQuery(path: string, params?: QueryParams): string {
  if (!params) {
    return path
  }
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value))
    }
  }
  const qs = search.toString()
  return qs ? `${path}?${qs}` : path
}

/** Build a client that attaches `Authorization: Bearer <token>` to each request. */
export function createApiClient(getToken: TokenGetter): ApiClient {
  /** Runs one attempt, retrying once with a fresh token on a 401. */
  async function fetchWithRetry(
    url: string,
    buildInit: (token: string | null) => RequestInit,
  ): Promise<Response> {
    const token = await getToken()
    const res = await fetch(url, buildInit(token))
    if (res.status !== 401) {
      return res
    }
    const freshToken = await getToken({ skipCache: true })
    return fetch(url, buildInit(freshToken))
  }

  async function toApiError(path: string, res: Response): Promise<ApiError> {
    let body: unknown
    try {
      body = await res.json()
    } catch {}
    return new ApiError(
      res.status,
      `Request to ${path} failed with ${res.status}`,
      body,
    )
  }

  async function request<T>(
    method: string,
    path: string,
    options: { body?: unknown; params?: QueryParams } = {},
  ): Promise<T> {
    const hasBody = options.body !== undefined
    const url = `${API_BASE_URL}${withQuery(path, options.params)}`
    const res = await fetchWithRetry(url, (token) => ({
      method,
      headers: {
        Accept: 'application/json',
        ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(hasBody ? { body: JSON.stringify(options.body) } : {}),
    }))
    if (!res.ok) {
      throw await toApiError(path, res)
    }
    if (res.status === 204) {
      return undefined as T
    }
    return (await res.json()) as T
  }

  return {
    get: (path, params) => request('GET', path, { params }),
    post: (path, body, params) => request('POST', path, { body, params }),
    patch: (path, body, params) => request('PATCH', path, { body, params }),
    del: (path, params) => request('DELETE', path, { params }),
    getBlob: async (path, params) => {
      const url = `${API_BASE_URL}${withQuery(path, params)}`
      const res = await fetchWithRetry(url, (token) => ({
        headers: {
          Accept: 'application/pdf',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      }))
      if (!res.ok) {
        throw await toApiError(path, res)
      }
      return res.blob()
    },
  }
}
