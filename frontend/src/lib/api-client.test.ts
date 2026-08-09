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

    const created = await api.post<{ id: string }>('/api/v1/companies', { name: 'Acme' })

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

    const error = (await api.get('/api/v1/companies').catch((e: unknown) => e)) as ApiError

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

    const error = (await api.getBlob('/api/v1/documents/missing').catch((e: unknown) => e)) as ApiError

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(404)
    expect(error.detail).toBe('Document not found')
  })
})
