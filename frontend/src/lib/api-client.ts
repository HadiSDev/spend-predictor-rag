import { API_BASE_URL } from './env'

/** Returns the current Clerk session token, or null when signed out. */
export type TokenGetter = () => Promise<string | null>

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
  // `loc` starts with the source ("body", "query"); only the leaf names a field.
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

  /**
   * The API's own explanation, for display. FastAPI puts it in `detail` — a
   * string for `HTTPException`, an array of `{msg, loc}` for 422 validation
   * errors. Falls back to the generic message when the body says nothing.
   */
  get detail(): string {
    const body = this.body
    if (typeof body !== 'object' || body === null || !('detail' in body)) return this.message
    const { detail } = body
    if (typeof detail === 'string' && detail) return detail
    if (Array.isArray(detail)) {
      const messages = detail.filter(isValidationDetail).map(formatValidationDetail).filter(Boolean)
      if (messages.length > 0) return messages.join('; ')
    }
    return this.message
  }
}

/** A typed, authenticated client for the web API bound to a token getter. */
export interface ApiClient {
  get: <T>(path: string, params?: QueryParams) => Promise<T>
  post: <T>(path: string, body?: unknown, params?: QueryParams) => Promise<T>
  patch: <T>(path: string, body?: unknown, params?: QueryParams) => Promise<T>
  /** `delete` is a reserved word; this is the DELETE verb. */
  del: <T>(path: string, params?: QueryParams) => Promise<T>
  /** Fetch a binary response (a PDF). `get` would try to parse it as JSON. */
  getBlob: (path: string, params?: QueryParams) => Promise<Blob>
}

function withQuery(path: string, params?: QueryParams): string {
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
    method: string,
    path: string,
    options: { body?: unknown; params?: QueryParams } = {},
  ): Promise<T> {
    const token = await getToken()
    const hasBody = options.body !== undefined
    const res = await fetch(`${API_BASE_URL}${withQuery(path, options.params)}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(hasBody ? { body: JSON.stringify(options.body) } : {}),
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
    // 204 carries no body — parsing it would throw.
    if (res.status === 204) return undefined as T
    return (await res.json()) as T
  }

  return {
    get: (path, params) => request('GET', path, { params }),
    post: (path, body, params) => request('POST', path, { body, params }),
    patch: (path, body, params) => request('PATCH', path, { body, params }),
    del: (path, params) => request('DELETE', path, { params }),
    getBlob: async (path, params) => {
      const token = await getToken()
      const res = await fetch(`${API_BASE_URL}${withQuery(path, params)}`, {
        headers: {
          Accept: 'application/pdf',
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
      return res.blob()
    },
  }
}
