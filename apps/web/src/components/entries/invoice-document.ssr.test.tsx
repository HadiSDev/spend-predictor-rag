// @vitest-environment node
//
// Everything else in this directory runs under jsdom with `react-pdf` mocked
// (see invoice-document.test.tsx) — deliberately, since jsdom cannot execute
// pdf.js at all. This file is the opposite: it runs with NO DOM globals
// whatsoever (no `window`, `document`, `DOMMatrix`, `Worker`, `canvas`) and
// the REAL `react-pdf`/`pdfjs-dist`, to prove the SSR guard actually holds
// rather than assuming React.lazy + Suspense is enough. TanStack Start's SSR
// is streaming (`renderToPipeableStream`), which — unlike the older
// `renderToString` — *does* attempt to resolve a suspended `React.lazy`
// import on the server, so the guard has to be `ClientOnly` (whose
// server snapshot is permanently "not hydrated"), not Suspense alone.
import * as React from 'react'
import { Writable } from 'node:stream'
import { describe, expect, it, vi } from 'vitest'
import { renderToPipeableStream } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { InvoiceDocument } from './invoice-document'
import { invoiceDocumentQueryOptions } from '#/lib/entries'
import type { ApiClient } from '#/lib/api-client'

vi.mock('#/lib/auth', () => ({
  useApi: (): ApiClient => ({
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
    getBlob: vi.fn(async () => new Blob(['%PDF-1.4'])),
  }),
}))

/** Collects a piped stream into a string and resolves once React is done
 *  with it — including any deferred (streamed-in) Suspense content. */
function renderToStreamedString(node: React.ReactElement): Promise<{ html: string; errors: Array<Error> }> {
  return new Promise((resolve) => {
    let html = ''
    const errors: Array<Error> = []
    const sink = new Writable({
      write(chunk: Buffer, _enc, cb) {
        html += chunk.toString()
        cb()
      },
    })
    sink.on('finish', () => resolve({ html, errors }))

    const { pipe } = renderToPipeableStream(node, {
      onShellReady() {
        pipe(sink)
      },
      onShellError(err: unknown) {
        errors.push(err as Error)
        resolve({ html, errors })
      },
      onError(err: unknown) {
        errors.push(err as Error)
      },
    })
  })
}

describe('react-pdf under plain Node (negative control)', () => {
  it('really does crash without a guard — DOMMatrix does not exist server-side', async () => {
    expect(typeof window).toBe('undefined')
    await expect(import('react-pdf')).rejects.toThrow(/DOMMatrix/)
  })
})

describe('InvoiceDocument — SSR safety', () => {
  it('never evaluates react-pdf while streaming the no-document state', async () => {
    const queryClient = new QueryClient()
    const { html, errors } = await renderToStreamedString(
      React.createElement(
        QueryClientProvider,
        { client: queryClient },
        React.createElement(InvoiceDocument, { invoiceId: null, filename: null }),
      ),
    )
    expect(errors).toEqual([])
    expect(html).toMatch(/no document/i)
  })

  it('never evaluates react-pdf while streaming with a document already cached', async () => {
    // Seed the cache so the query resolves synchronously with data on the
    // very first render pass — the closest SSR can get to the "rendered"
    // state, and exactly the case that would explode if the pdf.js import
    // were reachable on the server.
    const queryClient = new QueryClient()
    const options = invoiceDocumentQueryOptions(
      { getBlob: async () => new Blob(['%PDF-1.4']) } as unknown as ApiClient,
      'inv-1',
    )
    queryClient.setQueryData(options.queryKey, new Blob(['%PDF-1.4']))

    const { errors } = await renderToStreamedString(
      React.createElement(
        QueryClientProvider,
        { client: queryClient },
        React.createElement(InvoiceDocument, { invoiceId: 'inv-1', filename: 'x.pdf' }),
      ),
    )
    expect(errors).toEqual([])
  })

  it('the ClientOnly + lazy + Suspense guard, used exactly as invoice-document.tsx uses it, keeps the real react-pdf import from ever running on the server', async () => {
    const { ClientOnly } = await import('@tanstack/react-router')
    const LazyViewer = React.lazy(() => import('./invoice-document-viewer'))

    const { html, errors } = await renderToStreamedString(
      React.createElement(ClientOnly, {
        fallback: React.createElement('div', null, 'fallback-shown-on-the-server'),
        children: React.createElement(
          React.Suspense,
          { fallback: React.createElement('div', null, 'suspense-fallback') },
          React.createElement(LazyViewer, {
            url: 'blob:unused',
            scale: 1,
            pageNumber: 1,
            onDocumentLoad: () => {},
            onDocumentError: () => {},
          }),
        ),
      }),
    )

    expect(errors).toEqual([])
    expect(html).toContain('fallback-shown-on-the-server')
  })
})
