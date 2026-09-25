import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createApiClient } from './api-client'

function mockFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('createApiClient', () => {
  it('sends a POST with the JSON body and the bearer token', async () => {
    const fetchMock = mockFetch(jsonResponse({ id: 'c1', name: 'Acme' }, 201))
    const api = createApiClient(async () => 'tok-123')

    const created = await api.post<{ id: string }>('/api/v1/companies', {
      name: 'Acme',
    })

    expect(created.id).toBe('c1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/v1/companies')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ name: 'Acme' }))
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.headers.Authorization).toBe('Bearer tok-123')
  })

  it('omits Content-Type when there is no body', async () => {
    const fetchMock = mockFetch(jsonResponse({ ok: true }))
    const api = createApiClient(async () => 'tok-123')

    await api.get('/api/v1/companies', { include_inactive: true })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('include_inactive=true')
    expect(init.method).toBe('GET')
    expect(init.headers['Content-Type']).toBeUndefined()
    expect(init.body).toBeUndefined()
  })

  it('exposes FastAPI detail on a rejected write', async () => {
    mockFetch(jsonResponse({ detail: 'Slug already in use' }, 409))
    const api = createApiClient(async () => 'tok-123')

    const error = await api
      .patch('/api/v1/organization', { slug: 'taken' })
      .then(() => null)
      .catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(409)
    expect((error as ApiError).detail).toBe('Slug already in use')
  })

  it('flattens the 422 validation detail array', async () => {
    mockFetch(
      jsonResponse(
        { detail: [{ msg: 'Field required', loc: ['body', 'name'] }] },
        422,
      ),
    )
    const api = createApiClient(async () => null)

    const error = (await api
      .post('/api/v1/companies', {})
      .catch((e: unknown) => e)) as ApiError

    expect(error.detail).toBe('name: Field required')
  })

  it('falls back to the generic message when the body has no detail', async () => {
    mockFetch(new Response('nope', { status: 500 }))
    const api = createApiClient(async () => null)

    const error = (await api
      .get('/api/v1/companies')
      .catch((e: unknown) => e)) as ApiError

    expect(error.detail).toContain('500')
  })

  it('resolves a 204 without parsing a body', async () => {
    mockFetch(new Response(null, { status: 204 }))
    const api = createApiClient(async () => 'tok-123')

    await expect(api.del('/api/v1/organization')).resolves.toBeUndefined()
  })

  it('fetches a binary body with an Accept: application/pdf header', async () => {
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    const fetchMock = mockFetch(new Response(blob, { status: 200 }))
    const api = createApiClient(async () => 'tok-123')

    const result = await api.getBlob('/api/v1/documents/f1')

    expect(result).toBeInstanceOf(Blob)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/v1/documents/f1')
    expect(init.headers.Accept).toBe('application/pdf')
    expect(init.headers.Authorization).toBe('Bearer tok-123')
  })

  it('surfaces the JSON detail when a blob fetch fails', async () => {
    mockFetch(jsonResponse({ detail: 'Document not found' }, 404))
    const api = createApiClient(async () => 'tok-123')

    const error = (await api
      .getBlob('/api/v1/documents/missing')
      .catch((e: unknown) => e)) as ApiError

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(404)
    expect(error.detail).toBe('Document not found')
  })
})

describe('createApiClient 401 retry', () => {
  function tokenGetter() {
    return vi.fn(async (options?: { skipCache?: boolean }) =>
      options?.skipCache ? 'fresh-token' : 'stale-token',
    )
  }

  it('retries a GET exactly once with a freshly-minted token after a 401', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(jsonResponse({ id: 'c1' }))
    vi.stubGlobal('fetch', fetchMock)
    const getToken = tokenGetter()
    const api = createApiClient(getToken)

    const result = await api.get<{ id: string }>('/api/v1/companies')

    expect(result.id).toBe('c1')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(getToken.mock.calls[0]).toEqual([])
    expect(getToken).toHaveBeenNthCalledWith(2, { skipCache: true })
    const [, secondInit] = fetchMock.mock.calls[1]
    expect(secondInit.headers.Authorization).toBe('Bearer fresh-token')
  })

  it('retries a POST (with body) once on a 401 and resends the body', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(jsonResponse({ id: 'c1' }, 201))
    vi.stubGlobal('fetch', fetchMock)
    const getToken = tokenGetter()
    const api = createApiClient(getToken)

    const result = await api.post<{ id: string }>('/api/v1/companies', {
      name: 'Acme',
    })

    expect(result.id).toBe('c1')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [, secondInit] = fetchMock.mock.calls[1]
    expect(secondInit.body).toBe(JSON.stringify({ name: 'Acme' }))
    expect(secondInit.headers.Authorization).toBe('Bearer fresh-token')
  })

  it('retries getBlob once on a 401 with a fresh token', async () => {
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(blob, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const getToken = tokenGetter()
    const api = createApiClient(getToken)

    const result = await api.getBlob('/api/v1/documents/f1')

    expect(result).toBeInstanceOf(Blob)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [, secondInit] = fetchMock.mock.calls[1]
    expect(secondInit.headers.Authorization).toBe('Bearer fresh-token')
  })

  it('surfaces an ApiError when the retry also gets a 401', async () => {
    const fetchMock = mockFetch(new Response(null, { status: 401 }))
    const getToken = tokenGetter()
    const api = createApiClient(getToken)

    const error = (await api
      .get('/api/v1/companies')
      .catch((e: unknown) => e)) as ApiError

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(401)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(getToken).toHaveBeenCalledTimes(2)
  })

  it('does not retry a 403 — that is a permission answer, not a stale token', async () => {
    const fetchMock = mockFetch(
      jsonResponse({ detail: 'Insufficient permissions' }, 403),
    )
    const getToken = tokenGetter()
    const api = createApiClient(getToken)

    const error = (await api
      .get('/api/v1/companies')
      .catch((e: unknown) => e)) as ApiError

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(403)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(getToken).toHaveBeenCalledTimes(1)
  })
})
