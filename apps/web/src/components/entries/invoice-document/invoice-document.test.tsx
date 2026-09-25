import * as React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { InvoiceDocument } from './invoice-document'
import { ApiError } from '#/lib/api/api-client'
import type { ApiClient } from '#/lib/api/api-client'

const getBlob = vi.fn()

vi.mock('#/lib/auth/auth', () => ({
  useApi: (): ApiClient => ({
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
    getBlob,
  }),
}))

vi.mock('react-pdf', () => ({
  pdfjs: {
    GlobalWorkerOptions: {} as { workerSrc?: string },
    version: '5.4.296',
  },
  Document: ({
    file,
    onLoadSuccess,
    onLoadError,
    children,
  }: {
    file: string
    onLoadSuccess?: (pdf: { numPages: number }) => void
    onLoadError?: (error: Error) => void
    children?: React.ReactNode
  }) => {
    React.useEffect(() => {
      const behavior = documentBehavior
      if (behavior.kind === 'error') {
        onLoadError?.(new Error(behavior.message))
      } else {
        onLoadSuccess?.({ numPages: behavior.numPages })
      }
    }, [file])
    return <div data-testid="pdf-document">{children}</div>
  },
  Page: ({ pageNumber, scale }: { pageNumber: number; scale: number }) => (
    <div data-testid={`pdf-page-${pageNumber}`} data-scale={scale}>
      Page {pageNumber}
    </div>
  ),
}))

/** Controls what the mocked <Document> reports on load, per test. */
let documentBehavior:
  { kind: 'success'; numPages: number } | { kind: 'error'; message: string } = {
  kind: 'success',
  numPages: 3,
}

/** A controllable IntersectionObserver stand-in for jsdom. */
class MockIntersectionObserver implements IntersectionObserver {
  static instances: Array<MockIntersectionObserver> = []
  readonly root = null
  readonly rootMargin = ''
  readonly scrollMargin = ''
  readonly thresholds: ReadonlyArray<number> = []
  callback: IntersectionObserverCallback
  observed: Array<Element> = []

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    MockIntersectionObserver.instances.push(this)
  }
  observe(el: Element) {
    this.observed.push(el)
  }
  unobserve(el: Element) {
    this.observed = this.observed.filter((o) => o !== el)
  }
  disconnect() {
    this.observed = []
  }
  takeRecords(): Array<IntersectionObserverEntry> {
    return []
  }
  trigger(el: Element, isIntersecting: boolean) {
    this.callback(
      [{ target: el, isIntersecting } as IntersectionObserverEntry],
      this,
    )
  }
}

function setup(
  props: Partial<React.ComponentProps<typeof InvoiceDocument>> = {},
) {
  const queryClient = new QueryClient()
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <InvoiceDocument
        invoiceId="inv-1"
        filename="acme-invoice.pdf"
        {...props}
      />
    </QueryClientProvider>,
  )
  return { ...utils, queryClient }
}

let objectUrlCounter = 0

beforeEach(() => {
  documentBehavior = { kind: 'success', numPages: 3 }
  objectUrlCounter = 0
  MockIntersectionObserver.instances = []
  vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn(() => `blob:mock-${++objectUrlCounter}`),
      revokeObjectURL: vi.fn(),
    }),
  )
  Element.prototype.scrollIntoView = vi.fn()
  getBlob.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('InvoiceDocument — states', () => {
  it('tells the user when nothing is attached, without an empty viewer frame', () => {
    setup({ invoiceId: null, filename: null })
    expect(screen.getByText(/no document/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /download/i })).toBeNull()
    expect(getBlob).not.toHaveBeenCalled()
  })

  it('shows a skeleton while the document is loading, not a blank frame', () => {
    getBlob.mockReturnValue(new Promise(() => {}))
    const { container } = setup()
    expect(
      container.querySelectorAll('[class*="animate-pulse"]').length,
    ).toBeGreaterThan(0)
  })

  it('shows the API error detail and offers a retry that calls refetch', async () => {
    getBlob.mockRejectedValueOnce(
      new ApiError(502, 'Request failed', {
        detail: 'The ERP rejected the request.',
      }),
    )
    getBlob.mockResolvedValueOnce(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    setup()

    expect(
      await screen.findByText('The ERP rejected the request.'),
    ).toBeTruthy()
    expect(getBlob).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() => expect(getBlob).toHaveBeenCalledTimes(2))
    expect(await screen.findByTestId('pdf-document')).toBeTruthy()
  })

  it('renders the document once the blob resolves', async () => {
    getBlob.mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    setup()

    expect(await screen.findByText(/page 1 of 3/i)).toBeTruthy()
    expect(screen.getByTestId('pdf-document')).toBeTruthy()
  })

  it('shows an error, not a stuck loader, when the document fails to parse', async () => {
    documentBehavior = { kind: 'error', message: 'Invalid PDF structure.' }
    getBlob.mockResolvedValue(
      new Blob(['not a pdf'], { type: 'application/pdf' }),
    )
    setup()

    expect(await screen.findByText('Invalid PDF structure.')).toBeTruthy()
    expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy()
  })
})

describe('InvoiceDocument — media types', () => {
  it('renders an image attachment as an image, never through the PDF viewer', async () => {
    getBlob.mockResolvedValue(
      new Blob(['\xff\xd8\xff'], { type: 'image/jpeg' }),
    )
    setup({ filename: 'receipt.jpg' })

    const image = await screen.findByRole('img', { name: 'receipt.jpg' })
    expect(image.getAttribute('src')).toBe('blob:mock-1')
    expect(screen.queryByTestId('pdf-document')).toBeNull()
  })

  it('drops the page controls for an image, which has no pages', async () => {
    getBlob.mockResolvedValue(
      new Blob(['\xff\xd8\xff'], { type: 'image/jpeg' }),
    )
    setup({ filename: 'receipt.jpg' })
    await screen.findByRole('img')

    expect(screen.queryByRole('button', { name: /previous page/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /next page/i })).toBeNull()
    expect(screen.getByRole('button', { name: /zoom in/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /download/i })).toBeTruthy()
  })

  it('zooms an image with the same control that zooms a PDF', async () => {
    getBlob.mockResolvedValue(
      new Blob(['\xff\xd8\xff'], { type: 'image/jpeg' }),
    )
    setup({ filename: 'receipt.jpg' })
    const image = await screen.findByRole('img')

    expect(image.style.width).toBe('100%')
    fireEvent.click(screen.getByRole('button', { name: /zoom in/i }))
    expect(screen.getByRole('img').style.width).toBe('120%')
  })

  it('offers a download rather than a broken preview for a type it cannot show', async () => {
    getBlob.mockResolvedValue(
      new Blob(['PK'], { type: 'application/octet-stream' }),
    )
    setup({ filename: 'scan.dat' })

    expect(await screen.findByText(/cannot be previewed/i)).toBeTruthy()
    expect(screen.queryByTestId('pdf-document')).toBeNull()
    expect(screen.getByRole('button', { name: /download/i })).toBeTruthy()
  })

  it('reads the media type from the blob, ignoring any charset parameter', async () => {
    getBlob.mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf; charset=binary' }),
    )
    setup()
    expect(await screen.findByTestId('pdf-document')).toBeTruthy()
  })
})

describe('InvoiceDocument — object URL lifecycle', () => {
  it('creates an object URL from the fetched blob and revokes it on unmount', async () => {
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    getBlob.mockResolvedValue(blob)
    const { unmount } = setup()

    await screen.findByTestId('pdf-document')
    expect(URL.createObjectURL).toHaveBeenCalledWith(blob)
    const createdUrl = (URL.createObjectURL as ReturnType<typeof vi.fn>).mock
      .results[0]?.value

    unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(createdUrl)
  })
})

describe('InvoiceDocument — page controls', () => {
  it('steps through pages with previous/next, disabling at the ends', async () => {
    getBlob.mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    setup()
    await screen.findByText(/page 1 of 3/i)

    const prev = screen.getByRole('button', { name: /previous page/i })
    const next = screen.getByRole('button', { name: /next page/i })
    expect(prev.hasAttribute('disabled')).toBe(true)

    fireEvent.click(next)
    expect(screen.getByText(/page 2 of 3/i)).toBeTruthy()
    expect(prev.hasAttribute('disabled')).toBe(false)

    fireEvent.click(next)
    expect(screen.getByText(/page 3 of 3/i)).toBeTruthy()
    expect(next.hasAttribute('disabled')).toBe(true)

    fireEvent.click(prev)
    expect(screen.getByText(/page 2 of 3/i)).toBeTruthy()
  })

  it('zooms in and out within bounds', async () => {
    getBlob.mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    setup()
    await screen.findByTestId('pdf-document')

    const zoomIn = screen.getByRole('button', { name: /zoom in/i })
    const zoomOut = screen.getByRole('button', { name: /zoom out/i })

    expect(screen.getByText('100%')).toBeTruthy()
    fireEvent.click(zoomIn)
    expect(screen.getByText('120%')).toBeTruthy()
    fireEvent.click(zoomOut)
    fireEvent.click(zoomOut)
    expect(screen.getByText('80%')).toBeTruthy()
  })

  it('downloads the document under its original filename', async () => {
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    getBlob.mockResolvedValue(blob)
    setup({ filename: 'acme-invoice.pdf' })
    await screen.findByTestId('pdf-document')

    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})
    fireEvent.click(screen.getByRole('button', { name: /download/i }))

    expect(clickSpy).toHaveBeenCalledTimes(1)
    clickSpy.mockRestore()
  })

  it('gives every icon-only control an accessible name and a 44px hit area', async () => {
    getBlob.mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    setup()
    await screen.findByTestId('pdf-document')

    for (const name of [
      /previous page/i,
      /next page/i,
      /zoom out/i,
      /zoom in/i,
      /download/i,
    ]) {
      const button = screen.getByRole('button', { name })
      expect(button.getAttribute('aria-label')).toBeTruthy()
      expect(button.className).toMatch(/size-11/)
    }
  })
})

describe('InvoiceDocument — visible-page rendering', () => {
  it('does not rasterize a page until it has scrolled into view', async () => {
    getBlob.mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    setup()
    await screen.findByTestId('pdf-document')

    expect(screen.queryByTestId('pdf-page-2')).toBeNull()
    expect(screen.queryByTestId('pdf-page-3')).toBeNull()

    const slot2 = await screen.findByTestId('invoice-page-slot-2')
    const observerForSlot2 = await waitFor(() => {
      const observer = MockIntersectionObserver.instances.find((o) =>
        o.observed.includes(slot2),
      )
      if (!observer) {
        throw new Error('no observer for slot 2 yet')
      }
      return observer
    })

    observerForSlot2.trigger(slot2, true)
    expect(await screen.findByTestId('pdf-page-2')).toBeTruthy()
    expect(screen.queryByTestId('pdf-page-3')).toBeNull()
  })
})
